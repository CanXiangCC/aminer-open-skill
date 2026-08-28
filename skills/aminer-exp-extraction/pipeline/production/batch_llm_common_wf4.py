"""wf4 variant of process_llm_and_post.

Re-imports ``PaperJob`` / ``PaperBatchState`` / ``finalize_errored`` /
``_pipeline_stages`` from ``batch_llm_common`` (so the shared dataclass/enum/
error-helper cannot drift) and defines the wf4 stage split.

v0.7 Phase 2 split into two reusable halves so the staged pipeline can run
LLM HTTP and POST in different worker pools:

- ``run_qwen_http_stage`` : LLM_RUNNING timing + ``run_llm_stage_wf4`` +
  ``ctx.set``. Returns ``None`` on success or an error string when the paper
  must go straight to error-commit (skip-on-err: parse fail / empty LLM).
  HTTP-level exceptions propagate to the caller.
- ``run_post_stage``      : glue + W2/W3 waves + tail + timings, returns a
  built :class:`PaperFinalization` WITHOUT writing to disk.

``process_llm_and_post_wf4`` composes the two halves + immediate commit —
byte-identical behavior (timings, state transitions, error strings) to the
pre-split monolith, used by the legacy / chunked / global_batch paths.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from pipeline.production.batch_llm_common import (
    PaperBatchState,
    PaperJob,
    _pipeline_stages,
    finalize_errored,
)
from pipeline.production.monitor import utc_now
from pipeline.production.post_llm import (
    PaperFinalization,
    build_paper_finalization,
    commit_paper_finalization,
    run_wave_sync,
)
from pipeline.production.registry import get as get_extractor
from pipeline.production.workflows.spec import WorkflowSpec


def run_qwen_http_stage(
    job: PaperJob,
    *,
    spec: WorkflowSpec,
    llm_client,
    run_id: str,
    dry_run: bool,
    bert_mode: str = "serial",
    lock=None,
    llm_model_tag: str | None = None,
    ollama_format: str | None = None,
    num_predict_override: int | None = None,
    prompt_adapter: str | None = None,
    num_ctx_override: int | None = None,
    input_path: str | None = None,
) -> str | None:
    """LLM HTTP ONLY (the inference slot covers exactly this function).

    Mutates ``job.timings`` (llm_wait_sec / llm_started_at /
    llm_elapsed_sec) and sets the LLM partial on ``job.ctx``.

    Returns:
        ``None`` on success (POST may proceed), or an error string when the
        paper must skip POST and go to error-commit (parse fail / LLM error).
    Raises:
        Whatever the HTTP client raises — the caller owns the error string.
    """
    from pipeline.production.adapters.wf4_stages import run_llm_stage_wf4

    ctx = job.ctx

    def _set_state(state: PaperBatchState) -> None:
        if lock is not None:
            with lock:
                job.state = state
        else:
            job.state = state

    _set_state(PaperBatchState.LLM_RUNNING)
    llm_start_perf = time.perf_counter()
    bert_done_perf = job.timings.get("_bert_done_perf", llm_start_perf)
    job.timings["llm_wait_sec"] = round(max(0.0, llm_start_perf - bert_done_perf), 4)
    job.timings["llm_started_at"] = utc_now()

    llm_eid = spec.metadata.get("llm_extractor_id")  # WF4_LLM_EXTRACTOR_ID
    if dry_run:
        ctx.set(get_extractor(llm_eid).extract(ctx))  # base.extract returns _stub first
    else:
        _full_text = ctx.raw_md or (job.prepared.clean_stats or {}).get("merged_text") or ""
        _capture_env = os.environ.get("WF4_CAPTURE_DIR")
        _capture_dir = Path(_capture_env) if _capture_env else None
        llm_partial = run_llm_stage_wf4(
            job.prepared, job.bert_result, llm_client,
            run_id=run_id, bert_mode=bert_mode, llm_model_tag=llm_model_tag,
            ollama_format=ollama_format,
            num_predict_override=num_predict_override,
            prompt_adapter=prompt_adapter,
            num_ctx_override=num_ctx_override,
            input_path=input_path,
            full_text=_full_text,
            capture_dir=_capture_dir,
            capture_tag=job.paper_id,
        )
        ctx.set(llm_partial)
    job.timings["llm_elapsed_sec"] = round(time.perf_counter() - llm_start_perf, 4)

    # Skip-on-err: parse fail → no POST_LLM, no fabricated placeholder
    # experiment, no LLM retry. EXT-02: empty experiments after successful
    # parse is ok (continue).
    llm_partial = ctx.partials.get(llm_eid)
    llm_meta = llm_partial.metadata if isinstance(llm_partial.metadata, dict) else {}
    if llm_partial.status != "ok" or llm_meta.get("parse_error"):
        reason = llm_partial.error or llm_meta.get("parse_error") or "llm error"
        return f"llm_parse_or_empty: {reason}"
    return None


def run_post_stage(
    job: PaperJob,
    *,
    spec: WorkflowSpec,
    run_id: str,
    dry_run: bool,
    bert_mode: str = "serial",
    lock=None,
    input_path: str | None = None,
) -> PaperFinalization:
    """POST_LLM (glue + W2/W3 waves + tail) + build the finalization.

    Mutates ``job.timings`` (post_llm_elapsed_sec / paper_wall_sec /
    overlap_note). Returns the built :class:`PaperFinalization` WITHOUT
    writing anything — the caller (legacy path: immediately; staged path:
    the single writer) commits it.
    """
    ctx = job.ctx

    def _set_state(state: PaperBatchState) -> None:
        if lock is not None:
            with lock:
                job.state = state
        else:
            job.state = state

    _set_state(PaperBatchState.POST_LLM)
    post_start = time.perf_counter()
    spec.run_between_wave(ctx, finished_wave=1)  # _build_base_experiments_wf4

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
            ctx.set(get_extractor(eid).extract(ctx))  # rules.sample_size_policy_wf4
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
    if bert_mode == "skipped_struct":
        overlap_note = "nobert struct; bert skipped"
    elif input_path == "bert_struct":
        overlap_note = "bert struct 60; bert on"
    elif bert_mode == "batch":
        overlap_note = "bert batched globally; llm pipelined"
    else:
        overlap_note = "bert overlapped with other paper llm"
    job.timings["overlap_note"] = overlap_note

    return build_paper_finalization(
        ctx,
        spec,
        run_id=run_id,
        dry_run=dry_run,
        waves_log=waves_log,
        overall_start=job.paper_start_perf,
        error=None,
        pipeline_stages=_pipeline_stages(job),
        pipeline_started_at=job.timings.get("pipeline_started_at"),
    )


def process_llm_and_post_wf4(
    job: PaperJob,
    *,
    spec: WorkflowSpec,
    llm_client,
    run_id: str,
    dry_run: bool,
    bert_mode: str = "serial",
    lock=None,
    llm_model_tag: str | None = None,
    ollama_format: str | None = None,
    num_predict_override: int | None = None,
    prompt_adapter: str | None = None,
    num_ctx_override: int | None = None,
    input_path: str | None = None,
) -> None:
    """Run Stage-B (wf4 8-field) + glue + POST_LLM (W2/W3/tail) + finalize.

    Mutates ``job``: sets ``result`` + ``state`` (DONE|ERROR). Composes
    ``run_qwen_http_stage`` + ``run_post_stage`` + immediate commit —
    behavior identical to the pre-split monolith (same timings, states and
    error strings), used by legacy / chunked / global_batch paths.
    """
    def _set_state(state: PaperBatchState) -> None:
        if lock is not None:
            with lock:
                job.state = state
        else:
            job.state = state

    try:
        err = run_qwen_http_stage(
            job,
            spec=spec,
            llm_client=llm_client,
            run_id=run_id,
            dry_run=dry_run,
            bert_mode=bert_mode,
            lock=lock,
            llm_model_tag=llm_model_tag,
            ollama_format=ollama_format,
            num_predict_override=num_predict_override,
            prompt_adapter=prompt_adapter,
            num_ctx_override=num_ctx_override,
            input_path=input_path,
        )
        if err is not None:
            job.error = err
            _set_state(PaperBatchState.ERROR)
            finalize_errored(job, spec=spec, run_id=run_id, dry_run=dry_run)
            return
        fin = run_post_stage(
            job,
            spec=spec,
            run_id=run_id,
            dry_run=dry_run,
            bert_mode=bert_mode,
            lock=lock,
            input_path=input_path,
        )
        job.result = commit_paper_finalization(fin)
        _set_state(PaperBatchState.DONE)
    except Exception as exc:  # noqa: BLE001
        job.error = f"llm/post: {type(exc).__name__}: {exc}"
        _set_state(PaperBatchState.ERROR)
        finalize_errored(job, spec=spec, run_id=run_id, dry_run=dry_run)
