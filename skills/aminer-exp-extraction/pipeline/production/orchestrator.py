"""Production orchestrator: async Wave DAG scheduler.

T0  serial  : shared_preprocess (read md -> raw_md) + meta extractors
W1  parallel: llm.wf8 | rules.conclusion_limitations | rules.datasets.extract
    glue    : build base_experiments + experiments_stripped from LLM partial
W2  parallel: rules.datasets.assign | rules.evidence
W3  parallel: ml.domain | ml.experiment_type
T4  serial  : rules.sample_size_policy
T5  serial  : merge -> experiments[] + provenance -> write prediction/monitor

Within a wave, extractors run via ``asyncio.to_thread`` (sync pack/wf8 code in
worker threads). The orchestrator resolves extractors by id from the registry;
swapping a version never touches this file (criterion 6).
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from pipeline.production.context import PaperContext
from pipeline.production.monitor import utc_now
from pipeline.production.post_llm import ProductionResult, finalize_paper
from pipeline.production.registry import ensure_registered, get as get_extractor
from pipeline.production.workflows.spec import WorkflowSpec, get_workflow

__all__ = ["ProductionResult", "run_production_workflow"]


def _new_run_id() -> str:
    from datetime import datetime, timezone

    return f"prod-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def _read_md(md_path: Path) -> str:
    return md_path.read_text(encoding="utf-8")


async def _run_wave(ctx: PaperContext, extractor_ids: list[str]) -> tuple[float, list[dict[str, Any]]]:
    """Run one wave's extractors concurrently. Returns (elapsed_sec, extractor_dicts)."""
    if not extractor_ids:
        return 0.0, []
    start = time.perf_counter()

    async def _one(eid: str) -> dict[str, Any]:
        ext = get_extractor(eid)
        result = await asyncio.to_thread(ext.extract, ctx)
        ctx.set(result)
        return result.to_dict()

    # Run concurrently; order preserved via gather return list.
    dicts = await asyncio.gather(*[_one(eid) for eid in extractor_ids])
    elapsed = time.perf_counter() - start
    return elapsed, list(dicts)


def run_production_workflow(
    paper_id: str,
    workflow_id: str | None = None,
    *,
    md_path: Path | None = None,
    dry_run: bool = False,
    run_id: str | None = None,
) -> ProductionResult:
    """Synchronous entry point — runs the async DAG via asyncio.run."""
    ensure_registered()
    from pipeline.production.config import DEFAULT_WORKFLOW

    spec = get_workflow(workflow_id or DEFAULT_WORKFLOW)
    rid = run_id or _new_run_id()

    if md_path is None:
        from pipeline.production.config import DATA_MD_DIR, DEV10_MD_DIR

        for cand in (DATA_MD_DIR / f"{paper_id}.md", DEV10_MD_DIR / f"{paper_id}.md"):
            if cand.exists():
                md_path = cand
                break
        if md_path is None:
            return ProductionResult(
                paper_id=paper_id,
                run_id=rid,
                workflow_id=workflow_id,
                error=f"md file not found for paper {paper_id}",
            )

    return asyncio.run(_run_dag(paper_id, md_path, spec, rid, dry_run))


async def _run_dag(
    paper_id: str,
    md_path: Path,
    spec: WorkflowSpec,
    run_id: str,
    dry_run: bool,
) -> ProductionResult:
    ctx = PaperContext(
        paper_id=paper_id,
        md_path=md_path,
        run_id=run_id,
        workflow_id=spec.workflow_id,
        dry_run=dry_run,
    )

    waves_log: list[dict[str, Any]] = []
    overall_start = time.perf_counter()
    error: str | None = None

    try:
        # T0: shared preprocess + meta (serial).
        t0 = time.perf_counter()
        ctx.raw_md = await asyncio.to_thread(_read_md, md_path)
        for eid in ("meta.paper_id", "meta.placeholder"):
            ext = get_extractor(eid)
            ctx.set(await asyncio.to_thread(ext.extract, ctx))
        waves_log.append(
            {
                "wave": 0,
                "stage": "shared_preprocess+meta",
                "parallel": ["meta.paper_id", "meta.placeholder"],
                "elapsed_sec": round(time.perf_counter() - t0, 4),
                "started_at": utc_now(),
            }
        )

        # Waves 1..N
        for i, wave_ids in enumerate(spec.waves, start=1):
            wave_start = time.perf_counter()
            wave_started = utc_now()
            elapsed, _ = await _run_wave(ctx, wave_ids)
            waves_log.append(
                {
                    "wave": i,
                    "parallel": wave_ids,
                    "elapsed_sec": round(elapsed, 4),
                    "started_at": wave_started,
                }
            )
            # Inter-wave glue (workflow-provided hook, e.g. build experiments
            # from the LLM partial after Wave-1). Orchestrator stays generic.
            spec.run_between_wave(ctx, finished_wave=i)

        # Tail (serial).
        if spec.tail:
            t_tail = time.perf_counter()
            for eid in spec.tail:
                ext = get_extractor(eid)
                ctx.set(await asyncio.to_thread(ext.extract, ctx))
            waves_log.append(
                {
                    "wave": "tail",
                    "parallel": spec.tail,
                    "elapsed_sec": round(time.perf_counter() - t_tail, 4),
                    "started_at": utc_now(),
                }
            )

    except Exception as exc:  # noqa: BLE001 — top-level guard
        error = f"{type(exc).__name__}: {exc}"

    # T5: merge + write (shared with wf2 via post_llm.finalize_paper).
    return finalize_paper(
        ctx,
        spec,
        run_id=run_id,
        dry_run=dry_run,
        waves_log=waves_log,
        overall_start=overall_start,
        error=error,
    )
