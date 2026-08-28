"""BatchPipelineScheduler: cross-paper BERT ∥ LLM two-stage pipeline (prod-wf2).

Splits wf8's LLM into Stage-A (BERT, per-paper /filter) + Stage-B (LLM) and
pipelines them across papers: while paper n is in LLM, paper n+1 can be in
BERT (and paper n+2 in W1-rules). Field/merge/rule/ML semantics are identical
to prod-wf1 — only the batch entry point and LLM staging differ.

Per-paper lifecycle (matches prod-wf1 semantics; W2/W3/tail/merge run only
after this paper's LLM completes):
  PENDING → W1_RULES_RUNNING → BERT_QUEUED → BERT_RUNNING →
  LLM_QUEUED → LLM_RUNNING → POST_LLM → DONE | ERROR

Threading: queue.Queue + threading.Thread. bert_worker×bert_concurrency and
llm_worker×llm_concurrency; W1-rules per-paper threads (bounded). Each paper
has its own PaperContext (isolated). The ML pkl cache is global/read-only.

The llm + POST_LLM + finalize logic is shared with prod-wf3 via
``batch_llm_common.process_llm_and_post``.
"""

from __future__ import annotations

import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from pipeline.benchmark.stages.bert_client import SerialBertClient
from pipeline.benchmark.stages.llm_client import SingleLLMClient
from pipeline.production.adapters.wf8_stages import prepare_llm_inputs, run_bert_stage
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
_W1_RULES_WORKERS = 4  # max concurrent W1-rules threads (CPU-cheap)


class BatchPipelineScheduler:
    """Cross-paper BERT/LLM two-slot pipeline scheduler (wf2)."""

    def __init__(
        self,
        paper_ids: list[str],
        md_paths: dict[str, Path],
        run_id: str,
        spec: WorkflowSpec,
        *,
        bert_concurrency: int = 1,
        llm_concurrency: int = 1,
        dry_run: bool = False,
    ) -> None:
        ensure_registered()
        self.paper_ids = list(paper_ids)
        self.md_paths = md_paths
        self.run_id = run_id
        self.spec = spec
        self.bert_concurrency = bert_concurrency
        self.llm_concurrency = llm_concurrency
        self.dry_run = dry_run

        self.llm_eid: str = spec.metadata.get("llm_extractor_id", "llm.wf8_dev20_v2_wash")
        # Wave-1 minus the LLM extractor = the rule tasks that overlap BERT/LLM.
        self.w1_rule_ids: list[str] = [
            eid for eid in spec.waves[0] if eid != self.llm_eid
        ]

        self.bert_q: queue.Queue = queue.Queue()
        self.llm_q: queue.Queue = queue.Queue()
        self.jobs: dict[str, PaperJob] = {
            pid: PaperJob(paper_id=pid, md_path=md_paths[pid], run_id=run_id, spec=spec, dry_run=dry_run)
            for pid in self.paper_ids
        }
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ run

    def run(self) -> list:
        """Run the batch pipeline; return results in input order."""
        llm_workers = [
            threading.Thread(target=self._qwen_worker, name=f"llm-{i}", daemon=True)
            for i in range(self.llm_concurrency)
        ]
        bert_workers = [
            threading.Thread(target=self._bert_worker, name=f"bert-{i}", daemon=True)
            for i in range(self.bert_concurrency)
        ]
        for w in llm_workers:
            w.start()
        for w in bert_workers:
            w.start()

        # W1-rules producers (concurrent with BERT/LLM consumers).
        with ThreadPoolExecutor(max_workers=min(_W1_RULES_WORKERS, len(self.paper_ids) or 1)) as pool:
            list(pool.map(self._w1_rules, self.paper_ids))
        for _ in range(self.bert_concurrency):
            self.bert_q.put(_SENTINEL)

        for w in bert_workers:
            w.join()
        for _ in range(self.llm_concurrency):
            self.llm_q.put(_SENTINEL)
        for w in llm_workers:
            w.join()

        return [self.jobs[pid].result for pid in self.paper_ids]

    # ------------------------------------------------------------------ stages

    def _set_state(self, job: PaperJob, state: PaperBatchState) -> None:
        with self._lock:
            job.state = state

    def _w1_rules(self, paper_id: str) -> None:
        """Per-paper: read md + meta + W1-rules, then enqueue to bert_q."""
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
            run_wave_sync(ctx, ["meta.paper_id", "meta.placeholder"])
            if self.w1_rule_ids:
                run_wave_sync(ctx, self.w1_rule_ids)
            job.timings["w1_rules_elapsed_sec"] = round(time.perf_counter() - job.paper_start_perf, 4)
            job.timings["bert_queued_at"] = utc_now()
            self._set_state(job, PaperBatchState.BERT_QUEUED)
            self.bert_q.put(paper_id)
        except Exception as exc:  # noqa: BLE001
            job.error = f"w1_rules: {type(exc).__name__}: {exc}"
            self._set_state(job, PaperBatchState.ERROR)
            finalize_errored(job, spec=self.spec, run_id=self.run_id, dry_run=self.dry_run)

    def _bert_worker(self) -> None:
        """Consume bert_q: Stage-P + Stage-A (/filter), then enqueue to llm_q."""
        bert_client = SerialBertClient() if not self.dry_run else None
        while True:
            paper_id = self.bert_q.get()
            if paper_id is _SENTINEL:
                return
            job = self.jobs[paper_id]
            try:
                self._set_state(job, PaperBatchState.BERT_RUNNING)
                job.timings["bert_started_at"] = utc_now()
                t = time.perf_counter()
                if self.dry_run:
                    job.prepared = None
                    job.bert_result = None
                else:
                    job.prepared = prepare_llm_inputs(job.md_path)
                    job.bert_result = run_bert_stage(job.prepared, bert_client)
                job.timings["bert_elapsed_sec"] = round(time.perf_counter() - t, 4)
                job.timings["_bert_done_perf"] = time.perf_counter()
                job.timings["llm_queued_at"] = utc_now()
                self._set_state(job, PaperBatchState.LLM_QUEUED)
                self.llm_q.put(paper_id)
            except Exception as exc:  # noqa: BLE001
                job.error = f"bert: {type(exc).__name__}: {exc}"
                self._set_state(job, PaperBatchState.ERROR)
                finalize_errored(job, spec=self.spec, run_id=self.run_id, dry_run=self.dry_run)

    def _qwen_worker(self) -> None:
        """Consume llm_q: Stage-B + glue + POST_LLM + finalize (shared)."""
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
                bert_mode="serial",
                lock=self._lock,
            )
