"""Shared batch-pipeline pieces for wf2 (per-paper /filter) and wf3 (/filter/batch).

Holds the per-paper llm + POST_LLM + finalize logic (``process_llm_and_post``)
so wf2 and wf3 share identical downstream semantics; only the BERT stage differs.
Also holds PaperBatchState / PaperJob / _pipeline_stages / finalize_errored.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from pipeline.production.context import PaperContext
from pipeline.production.monitor import utc_now
from pipeline.production.post_llm import ProductionResult, finalize_paper, run_wave_sync
from pipeline.production.registry import get as get_extractor
from pipeline.production.workflows.spec import WorkflowSpec


class PaperBatchState(str, Enum):
    PENDING = "PENDING"
    W1_RULES_RUNNING = "W1_RULES_RUNNING"
    BERT_QUEUED = "BERT_QUEUED"
    BERT_RUNNING = "BERT_RUNNING"
    LLM_QUEUED = "LLM_QUEUED"
    LLM_RUNNING = "LLM_RUNNING"
    POST_LLM = "POST_LLM"
    DONE = "DONE"
    ERROR = "ERROR"
    # v0.7 Phase 2 staged-pipeline-only states (legacy paths never set these).
    PREP_QUEUED = "PREP_QUEUED"
    PREP_RUNNING = "PREP_RUNNING"
    POST_QUEUED = "POST_QUEUED"
    WRITE_QUEUED = "WRITE_QUEUED"
    COMMITTED_SUCCESS = "COMMITTED_SUCCESS"
    COMMITTED_ERROR = "COMMITTED_ERROR"


@dataclass
class PaperJob:
    paper_id: str
    # Path | None: rolling admission strips md_path to None after the durable
    # commit (heavy-field release); PREP asserts it is set before reading.
    md_path: Path | None
    run_id: str
    spec: WorkflowSpec
    dry_run: bool
    state: PaperBatchState = PaperBatchState.PENDING
    ctx: PaperContext | None = None
    prepared: Any = None
    bert_result: Any = None
    timings: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    result: ProductionResult | None = None
    paper_start_perf: float = 0.0


def _pipeline_stages(job: PaperJob) -> dict[str, Any]:
    """Public pipeline_stages dict (drops private perf-counter keys)."""
    return {k: v for k, v in job.timings.items() if not k.startswith("_")}


def process_llm_and_post(
    job: PaperJob,
    *,
    spec: WorkflowSpec,
    llm_client,
    run_id: str,
    dry_run: bool,
    bert_mode: str = "serial",
    lock=None,
) -> None:
    """Run Stage-B + glue + POST_LLM (W2/W3/tail) + finalize for one paper.

    Mutates ``job``: sets ``result`` + ``state`` (DONE|ERROR). ``bert_mode`` is
    forwarded to ``run_qwen_stage`` provenance. The llm wait is computed from
    ``job.timings["_bert_done_perf"]`` (set by the BERT stage — wf2 bert_worker
    or wf3 batch phase).
    """
    from pipeline.production.adapters.wf8_stages import run_qwen_stage

    ctx = job.ctx

    def _set_state(state: PaperBatchState) -> None:
        if lock is not None:
            with lock:
                job.state = state
        else:
            job.state = state

    try:
        _set_state(PaperBatchState.LLM_RUNNING)
        llm_start_perf = time.perf_counter()
        bert_done_perf = job.timings.get("_bert_done_perf", llm_start_perf)
        job.timings["llm_wait_sec"] = round(max(0.0, llm_start_perf - bert_done_perf), 4)
        job.timings["llm_started_at"] = utc_now()

        llm_eid = spec.metadata.get("llm_extractor_id", "llm.wf8_dev20_v2_wash")
        if dry_run:
            ctx.set(get_extractor(llm_eid).extract(ctx))
        else:
            llm_partial = run_qwen_stage(
                job.prepared, job.bert_result, llm_client, run_id=run_id, bert_mode=bert_mode
            )
            ctx.set(llm_partial)
        job.timings["llm_elapsed_sec"] = round(time.perf_counter() - llm_start_perf, 4)

        _set_state(PaperBatchState.POST_LLM)
        post_start = time.perf_counter()
        spec.run_between_wave(ctx, finished_wave=1)

        waves_log: list[dict[str, Any]] = []
        for idx, wave_ids in enumerate(spec.waves[1:], start=2):
            t = time.perf_counter()
            started = utc_now()
            run_wave_sync(ctx, wave_ids)
            waves_log.append(
                {
                    "wave": idx,
                    "parallel": wave_ids,
                    "elapsed_sec": round(time.perf_counter() - t, 4),
                    "started_at": started,
                }
            )
            spec.run_between_wave(ctx, finished_wave=idx)
        if spec.tail:
            t = time.perf_counter()
            started = utc_now()
            for eid in spec.tail:
                ctx.set(get_extractor(eid).extract(ctx))
            waves_log.append(
                {
                    "wave": "tail",
                    "parallel": list(spec.tail),
                    "elapsed_sec": round(time.perf_counter() - t, 4),
                    "started_at": started,
                }
            )
        job.timings["post_llm_elapsed_sec"] = round(time.perf_counter() - post_start, 4)
        job.timings["paper_wall_sec"] = round(time.perf_counter() - job.paper_start_perf, 4)
        job.timings["overlap_note"] = (
            "bert batched globally; llm pipelined"
            if bert_mode == "batch"
            else "bert overlapped with other paper llm"
        )

        result = finalize_paper(
            ctx,
            spec,
            run_id=run_id,
            dry_run=dry_run,
            waves_log=waves_log,
            overall_start=job.paper_start_perf,
            error=None,
            pipeline_stages=_pipeline_stages(job),
        )
        job.result = result
        _set_state(PaperBatchState.DONE)
    except Exception as exc:  # noqa: BLE001
        job.error = f"llm/post: {type(exc).__name__}: {exc}"
        _set_state(PaperBatchState.ERROR)
        finalize_errored(job, spec=spec, run_id=run_id, dry_run=dry_run)


def build_errored_finalization(
    job: PaperJob, *, spec: WorkflowSpec, run_id: str, dry_run: bool
) -> "PaperFinalization":
    """Build (without writing) the error finalization for a failed paper.

    v0.7 Phase 2: staged pipelines commit this via their single writer
    instead of writing inline. ``finalize_errored`` = build + commit.
    """
    from pipeline.production.post_llm import build_paper_finalization

    ctx = job.ctx or PaperContext(
        paper_id=job.paper_id,
        md_path=job.md_path,
        run_id=run_id,
        workflow_id=spec.workflow_id,
        dry_run=dry_run,
    )
    try:
        job.timings["paper_wall_sec"] = round(time.perf_counter() - job.paper_start_perf, 4)
    except Exception:  # noqa: BLE001
        pass
    return build_paper_finalization(
        ctx,
        spec,
        run_id=run_id,
        dry_run=dry_run,
        waves_log=[],
        overall_start=job.paper_start_perf,
        error=job.error,
        pipeline_stages=_pipeline_stages(job) if job.timings else None,
        pipeline_started_at=job.timings.get("pipeline_started_at") if job.timings else None,
    )


def finalize_errored(
    job: PaperJob, *, spec: WorkflowSpec, run_id: str, dry_run: bool
) -> None:
    """Write an error prediction/monitor for a failed paper."""
    from pipeline.production.post_llm import commit_paper_finalization

    job.result = commit_paper_finalization(
        build_errored_finalization(job, spec=spec, run_id=run_id, dry_run=dry_run)
    )
