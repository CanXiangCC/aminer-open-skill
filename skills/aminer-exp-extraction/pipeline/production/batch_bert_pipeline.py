"""BatchBertPipelineScheduler: cross-paper /filter/batch + LLM pipeline (prod-wf3).

Single variable vs prod-wf2: the 10x per-paper ``POST /filter`` (bert_worker) is
replaced by one (or few chunked) ``POST /filter/batch`` — a single server-side
GPU mini-batch across papers. W1-rules, Stage-P ``prepare_llm_inputs``, the LLM
cross-paper pipeline, POST_LLM, and field/merge semantics are identical to wf2.

Three phases (no bert_q, no bert_worker):
  PREP       (per-paper thread): meta + W1-rules + prepare_llm_inputs -> LlmPrepared
  BERT-BATCH (global, main):     run_bert_batch_for_papers -> per-paper BertStageResult
  LLM       (llm_worker x N):  Stage-B (bert_mode="batch") + glue + POST_LLM + finalize

The llm + POST_LLM + finalize logic is shared with wf2 via
``batch_llm_common.process_llm_and_post``.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from pipeline.benchmark.stages.llm_client import SingleLLMClient
from pipeline.production.adapters.wf8_stages import (
    LlmPrepared,
    prepare_llm_inputs,
    run_bert_batch_for_papers,
)
from pipeline.production.batch_llm_common import (
    PaperBatchState,
    PaperJob,
    finalize_errored,
    process_llm_and_post,
)
from pipeline.production.context import PaperContext
from pipeline.production.monitor import utc_now
from pipeline.production.post_llm import run_wave_sync
from pipeline.production.registry import ensure_registered
from pipeline.production.workflows.spec import WorkflowSpec

_SENTINEL = object()
_PREP_WORKERS = 4


class BatchBertPipelineScheduler:
    """Cross-paper /filter/batch + LLM pipeline scheduler (wf3)."""

    def __init__(
        self,
        paper_ids: list[str],
        md_paths: dict[str, Path],
        run_id: str,
        spec: WorkflowSpec,
        *,
        llm_concurrency: int = 1,
        bert_batch_size: int = 32,
        bert_chunk_papers: int = 0,
        dry_run: bool = False,
    ) -> None:
        ensure_registered()
        self.paper_ids = list(paper_ids)
        self.md_paths = md_paths
        self.run_id = run_id
        self.spec = spec
        self.llm_concurrency = llm_concurrency
        self.bert_batch_size = bert_batch_size
        # 0/None -> auto (one shot unless large); >0 -> force papers per chunk.
        self.bert_chunk_papers = bert_chunk_papers or None
        self.dry_run = dry_run

        self.llm_eid: str = spec.metadata.get("llm_extractor_id", "llm.wf8_dev20_v2_wash")
        self.w1_rule_ids: list[str] = [
            eid for eid in spec.waves[0] if eid != self.llm_eid
        ]

        self.llm_q: queue.Queue = queue.Queue()
        self.jobs: dict[str, PaperJob] = {
            pid: PaperJob(paper_id=pid, md_path=md_paths[pid], run_id=run_id, spec=spec, dry_run=dry_run)
            for pid in self.paper_ids
        }
        self._lock = threading.Lock()
        self.batch_monitor: dict[str, Any] | None = None

    # ------------------------------------------------------------------ run

    def run(self) -> list:
        # Phase 1: PREP (per-paper W1-rules + Stage-P).
        with ThreadPoolExecutor(max_workers=min(_PREP_WORKERS, len(self.paper_ids) or 1)) as pool:
            list(pool.map(self._prep_paper, self.paper_ids))

        # Phase 2: BERT-BATCH (global). Only papers with prepared set.
        self._run_bert_batch()

        # Phase 3: LLM pipeline (consumes llm_q).
        llm_workers = [
            threading.Thread(target=self._qwen_worker, name=f"llm-{i}", daemon=True)
            for i in range(self.llm_concurrency)
        ]
        for w in llm_workers:
            w.start()
        for _ in range(self.llm_concurrency):
            self.llm_q.put(_SENTINEL)
        for w in llm_workers:
            w.join()

        return [self.jobs[pid].result for pid in self.paper_ids]

    # ------------------------------------------------------------------ phases

    def _set_state(self, job: PaperJob, state: PaperBatchState) -> None:
        with self._lock:
            job.state = state

    def _prep_paper(self, paper_id: str) -> None:
        """Phase 1: read md + meta + W1-rules + Stage-P prepare_llm_inputs."""
        job = self.jobs[paper_id]
        job.paper_start_perf = time.perf_counter()
        job.timings["w1_rules_started_at"] = utc_now()
        try:
            ctx = PaperContext(
                paper_id=paper_id,
                md_path=job.md_path,
                run_id=self.run_id,
                workflow_id=self.spec.workflow_id,
                dry_run=self.dry_run,
            )
            job.ctx = ctx
            self._set_state(job, PaperBatchState.W1_RULES_RUNNING)
            ctx.raw_md = job.md_path.read_text(encoding="utf-8")
            prep_start = time.perf_counter()
            run_wave_sync(ctx, ["meta.paper_id", "meta.placeholder"])
            if self.w1_rule_ids:
                run_wave_sync(ctx, self.w1_rule_ids)
            if not self.dry_run:
                job.prepared = prepare_llm_inputs(job.md_path)
            job.timings["w1_rules_elapsed_sec"] = round(time.perf_counter() - job.paper_start_perf, 4)
            job.timings["prep_elapsed_sec"] = round(time.perf_counter() - prep_start, 4)
        except Exception as exc:  # noqa: BLE001
            job.error = f"prep: {type(exc).__name__}: {exc}"
            self._set_state(job, PaperBatchState.ERROR)
            finalize_errored(job, spec=self.spec, run_id=self.run_id, dry_run=self.dry_run)

    def _run_bert_batch(self) -> None:
        """Phase 2: one /filter/batch across all prepared papers."""
        prepared_map: dict[str, LlmPrepared] = {
            pid: self.jobs[pid].prepared
            for pid in self.paper_ids
            if self.jobs[pid].prepared is not None
        }
        if not prepared_map or self.dry_run:
            # Nothing to batch (all errored) or dry-run: mark bert done, enqueue.
            batch_done_perf = time.perf_counter()
            for pid in self.paper_ids:
                job = self.jobs[pid]
                if job.state == PaperBatchState.ERROR:
                    continue
                job.timings["bert_mode"] = "batch" if not self.dry_run else "stub"
                job.timings["bert_elapsed_sec"] = 0.0
                job.timings["_bert_done_perf"] = batch_done_perf
                job.timings["llm_queued_at"] = utc_now()
                self._set_state(job, PaperBatchState.LLM_QUEUED)
                self.llm_q.put(pid)
            self.batch_monitor = None
            return

        batch_started = utc_now()
        results, batch_monitor = run_bert_batch_for_papers(
            prepared_map,
            chunk_max_papers=self.bert_chunk_papers,
            batch_size=self.bert_batch_size,
        )
        batch_done_perf = time.perf_counter()
        self.batch_monitor = batch_monitor
        self._write_bert_batch_monitor(batch_monitor)

        for pid in self.paper_ids:
            job = self.jobs[pid]
            if job.state == PaperBatchState.ERROR:
                continue
            bert_res = results.get(pid)
            if bert_res is None:
                job.error = "bert_batch: no result for paper"
                self._set_state(job, PaperBatchState.ERROR)
                finalize_errored(job, spec=self.spec, run_id=self.run_id, dry_run=self.dry_run)
                continue
            job.bert_result = bert_res
            job.timings["bert_mode"] = "batch"
            job.timings["bert_batch_chunk"] = bert_res.timings.get("bert_batch_chunk", 0)
            job.timings["bert_amortized_sec"] = bert_res.timings.get("bert_amortized_sec", 0.0)
            job.timings["bert_elapsed_sec"] = 0.0
            job.timings["_bert_done_perf"] = batch_done_perf
            job.timings["llm_queued_at"] = utc_now()
            self._set_state(job, PaperBatchState.LLM_QUEUED)
            self.llm_q.put(pid)

    def _qwen_worker(self) -> None:
        """Phase 3: Stage-B (batch mode) + glue + POST_LLM + finalize (shared)."""
        llm_client = SingleLLMClient() if not self.dry_run else None
        while True:
            paper_id = self.llm_q.get()
            if paper_id is _SENTINEL:
                return
            job = self.jobs[paper_id]
            process_llm_and_post(
                job,
                spec=self.spec,
                llm_client=llm_client,
                run_id=self.run_id,
                dry_run=self.dry_run,
                bert_mode="batch" if not self.dry_run else "serial",
                lock=self._lock,
            )

    # ------------------------------------------------------------------ monitor

    def _write_bert_batch_monitor(self, batch_monitor: dict[str, Any]) -> None:
        from pipeline.production.config import RUNS_DIR

        run_dir = RUNS_DIR / self.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        payload = {"run_id": self.run_id, "workflow_id": self.spec.workflow_id, **batch_monitor}
        (run_dir / "bert_batch_monitor.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
