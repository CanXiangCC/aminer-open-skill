"""Shared POST_LLM helpers for wf1 (async) and wf2 (sync batch pipeline).

- ``run_wave_sync``  : sync parallel wave runner (ThreadPoolExecutor) for wf2's
  in-thread POST_LLM (W2/W3) — mirrors orchestrator._run_wave but without asyncio.
- ``finalize_paper`` : merge -> monitor -> write prediction/monitor/partials ->
  append history. Extracted from orchestrator so wf1 and wf2 share identical
  output writing. wf1 behavior is unchanged (regression-checked).
- v0.7 Phase 2 split: ``finalize_paper`` = ``build_paper_finalization`` (no
  filesystem side effects) + ``commit_paper_finalization`` (durable write).
  Legacy callers keep the composed wrapper; the staged pipeline calls the
  halves separately so a single writer thread does all committing.
"""

from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipeline.production.config import RUNS_DIR
from pipeline.production.context import PaperContext
from pipeline.production.merge import ProductionMerger
from pipeline.production.monitor import (
    append_history,
    build_paper_monitor,
    utc_now,
    write_paper_monitor,
)
from pipeline.production.registry import get as get_extractor
from pipeline.production.test_hooks import barrier as _phase3_barrier
from pipeline.production.workflows.spec import WorkflowSpec


@dataclass
class ProductionResult:
    paper_id: str
    run_id: str
    workflow_id: str
    experiments: list[dict[str, Any]] = field(default_factory=list)
    provenance: list[dict[str, Any]] = field(default_factory=list)
    monitor: dict[str, Any] = field(default_factory=dict)
    prediction_path: Path | None = None
    monitor_path: Path | None = None
    error: str | None = None


@dataclass
class PaperFinalization:
    """Build-step output of :func:`build_paper_finalization`.

    Everything needed to durably commit one paper, with NO side effects yet:
    the staged (v0.7 Phase 2) pipeline builds finalizations in POST workers
    and commits them in the single writer thread.
    """

    paper_id: str
    run_id: str
    workflow_id: str
    dry_run: bool
    prediction: dict[str, Any]
    monitor: dict[str, Any]
    pred_path: Path
    mon_path: Path
    experiments: list[dict[str, Any]]
    provenance: list[dict[str, Any]]
    error: str | None
    # extractor_id -> already-serialized partial payload ({} when dry_run)
    partials: dict[str, dict[str, Any]] = field(default_factory=dict)
    # history record WITHOUT the "ts" key — stamped at commit time
    history_record: dict[str, Any] | None = None


def run_wave_sync(ctx: PaperContext, extractor_ids: list[str]) -> float:
    """Run one wave's extractors concurrently (sync). Returns elapsed_sec.

    Each extractor runs in a worker thread; results are set on ctx. Mirrors
    ``orchestrator._run_wave`` but synchronous, for wf2's in-thread POST_LLM.
    """
    if not extractor_ids:
        return 0.0
    start = time.perf_counter()

    def _one(eid: str) -> None:
        ext = get_extractor(eid)
        result = ext.extract(ctx)  # FieldExtractor.extract is sync + self-guards
        ctx.set(result)

    with ThreadPoolExecutor(max_workers=len(extractor_ids)) as pool:
        list(pool.map(_one, extractor_ids))
    return time.perf_counter() - start


def _write_partials(ctx: PaperContext, run_id: str) -> None:
    """Persist each extractor partial for A/B (D7)."""
    from pipeline.production.config import PARTIALS_DIR

    for eid, result in ctx.partials.items():
        d = PARTIALS_DIR / eid / f"{ctx.paper_id}.json"
        d.parent.mkdir(parents=True, exist_ok=True)
        payload = result.to_dict()
        payload["value"] = result.value
        payload["paper_id"] = ctx.paper_id
        payload["run_id"] = run_id
        d.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def build_paper_finalization(
    ctx: PaperContext,
    spec: WorkflowSpec,
    *,
    run_id: str,
    dry_run: bool,
    waves_log: list[dict[str, Any]],
    overall_start: float,
    error: str | None = None,
    pipeline_stages: dict[str, Any] | None = None,
    pipeline_started_at: str | None = None,
) -> PaperFinalization:
    """Build the finalization (merge/monitor/prediction) WITHOUT writing.

    Pure w.r.t. the filesystem: everything ``commit_paper_finalization``
    needs is captured on the returned :class:`PaperFinalization`, so the
    staged pipeline can build in a POST worker and commit in the writer.
    """
    merge_conflicts: list[dict[str, Any]] = []
    experiments: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []
    if error is None:
        merger_name = spec.metadata.get("merger", "production")
        if merger_name == "wf4":
            from pipeline.production.merge_wf4 import MergerWf4

            experiments, provenance, merge_conflicts = MergerWf4().merge(ctx)
        else:
            experiments, provenance, merge_conflicts = ProductionMerger().merge(ctx)

    total_elapsed = time.perf_counter() - overall_start
    critical_path = sum(w.get("elapsed_sec", 0) for w in waves_log)
    extractors_log = [r.to_dict() for r in ctx.partials.values()]

    monitor = build_paper_monitor(
        ctx,
        waves=waves_log,
        extractors=extractors_log,
        critical_path_sec=critical_path,
        merge_conflicts=merge_conflicts,
        total_elapsed_sec=total_elapsed,
        error=error,
        pipeline_stages=pipeline_stages,
        pipeline_started_at=pipeline_started_at,
    )

    run_dir = RUNS_DIR / run_id
    pred_dir = run_dir / "predictions"
    mon_dir = run_dir / "monitors"

    llm_eid = spec.metadata.get("llm_extractor_id")
    llm_meta = ctx.partials.get(llm_eid) if llm_eid else None
    paper_title = ""
    if llm_meta and isinstance(llm_meta.metadata, dict):
        paper_title = llm_meta.metadata.get("paper_title", "")

    merger_name = spec.metadata.get("merger", "production")
    research_problem = ""
    research_problem_description = ""
    research_problem_aliases: list[Any] = []
    if merger_name == "wf4" and llm_meta and llm_meta.status == "ok":
        llm_val = llm_meta.value if isinstance(llm_meta.value, dict) else {}
        research_problem = llm_val.get("research_problem", "") or ""
        research_problem_description = llm_val.get("research_problem_description", "") or ""
        rp_aliases = llm_val.get("research_problem_aliases")
        research_problem_aliases = rp_aliases if isinstance(rp_aliases, list) else []

    prediction = {
        "paper_id": ctx.paper_id,
        "paper_title": paper_title,
        "workflow_id": spec.workflow_id,
        "workflow_version": spec.workflow_version,
        "run_id": run_id,
        "dry_run": dry_run,
        "experiments": experiments,
        "provenance": provenance,
    }
    if merger_name == "wf4":
        prediction["research_problem"] = research_problem
        prediction["research_problem_description"] = research_problem_description
        prediction["research_problem_aliases"] = research_problem_aliases
    if error is not None:
        # Persist the failure marker so resume logic (run_paths.prediction_ok)
        # can distinguish failed papers from successfully completed ones.
        prediction["error"] = error
    pred_path = pred_dir / f"{ctx.paper_id}.json"
    mon_path = mon_dir / f"{ctx.paper_id}_monitor.json"

    partials_payloads: dict[str, dict[str, Any]] = {}
    if not dry_run:
        for eid, result in ctx.partials.items():
            payload = result.to_dict()
            payload["value"] = result.value
            payload["paper_id"] = ctx.paper_id
            payload["run_id"] = run_id
            partials_payloads[eid] = payload

    history_record: dict[str, Any] | None = None
    if not dry_run:
        history_record = {
            "run_id": run_id,
            "paper_id": ctx.paper_id,
            "workflow_id": spec.workflow_id,
            "workflow_version": spec.workflow_version,
            "dry_run": dry_run,
            "critical_path_sec": round(critical_path, 4),
            "total_elapsed_sec": round(total_elapsed, 4),
            "extractor_statuses": {r.extractor_id: r.status for r in ctx.partials.values()},
            "merge_conflict_count": len(merge_conflicts),
            "experiment_count": len(experiments),
            "error": error,
        }

    return PaperFinalization(
        paper_id=ctx.paper_id,
        run_id=run_id,
        workflow_id=spec.workflow_id,
        dry_run=dry_run,
        prediction=prediction,
        monitor=monitor,
        pred_path=pred_path,
        mon_path=mon_path,
        experiments=experiments,
        provenance=provenance,
        error=error,
        partials=partials_payloads,
        history_record=history_record,
    )


def commit_paper_finalization(fin: PaperFinalization) -> ProductionResult:
    """Durably commit one built finalization (single-writer safe).

    Write order matches the pre-split ``finalize_paper`` exactly:
    prediction (tmp + os.replace) -> paper monitor -> partials -> history.
    """
    pred_path = fin.pred_path
    pred_path.parent.mkdir(parents=True, exist_ok=True)
    fin.mon_path.parent.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(fin.prediction, indent=2, ensure_ascii=False, default=str)
    tmp_path = pred_path.with_suffix(pred_path.suffix + ".tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    _phase3_barrier("replace")
    os.replace(tmp_path, pred_path)

    # Completion ledger (TODO-V07-11): file-first-then-ledger. Best effort —
    # a failed append never fails the commit; a missing row is backfilled
    # from the file at compaction time.
    if not fin.dry_run:
        try:
            from pipeline.production import completion_ledger

            session_run_id, job_batch_id = completion_ledger.split_run_id(fin.run_id)
            completion_ledger.append_row(
                session_run_id,
                job_batch_id,
                fin.run_id,
                fin.paper_id,
                "error" if fin.error else "ok",
                error_class=fin.error,
                experiments=len(fin.experiments),
                prediction_payload=payload,
                workflow_version=fin.prediction.get("workflow_version"),
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"[completion_ledger] append failed for {fin.run_id}/{fin.paper_id}: {exc}",
                file=sys.stderr,
            )

    mon_path: Path | None = None
    if os.environ.get("PROD_SKIP_PAPER_MONITOR", "").strip() not in ("1", "true", "True"):
        mon_path = fin.mon_path
        write_paper_monitor(fin.monitor, mon_path)

    if not fin.dry_run:
        from pipeline.production.config import PARTIALS_DIR

        for eid, partial_payload in fin.partials.items():
            d = PARTIALS_DIR / eid / f"{fin.paper_id}.json"
            d.parent.mkdir(parents=True, exist_ok=True)
            d.write_text(
                json.dumps(partial_payload, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        if fin.history_record is not None:
            record = {"ts": utc_now(), **fin.history_record}
            append_history(record)

    return ProductionResult(
        paper_id=fin.paper_id,
        run_id=fin.run_id,
        workflow_id=fin.workflow_id,
        experiments=fin.experiments,
        provenance=fin.provenance,
        monitor=fin.monitor,
        prediction_path=pred_path,
        monitor_path=mon_path,
        error=fin.error,
    )


def finalize_paper(
    ctx: PaperContext,
    spec: WorkflowSpec,
    *,
    run_id: str,
    dry_run: bool,
    waves_log: list[dict[str, Any]],
    overall_start: float,
    error: str | None = None,
    pipeline_stages: dict[str, Any] | None = None,
) -> ProductionResult:
    """Merge -> monitor -> write prediction/monitor/partials -> history.

    Shared by wf1 (pipeline_stages=None) and wf2 (pipeline_stages set).
    Unchanged composition: build + immediately commit. The staged (v0.7
    Phase 2) pipeline calls the two halves separately.
    """
    fin = build_paper_finalization(
        ctx,
        spec,
        run_id=run_id,
        dry_run=dry_run,
        waves_log=waves_log,
        overall_start=overall_start,
        error=error,
        pipeline_stages=pipeline_stages,
    )
    return commit_paper_finalization(fin)
