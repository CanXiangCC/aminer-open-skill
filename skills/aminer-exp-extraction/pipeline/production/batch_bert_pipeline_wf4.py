"""BatchBertPipelineSchedulerWf4: wf4 /filter/batch + LLM pipeline (prod-wf4).

A copy of ``BatchBertPipelineScheduler`` (wf3) with three import swaps:
  - PREP        : ``prepare_llm_inputs``    -> ``prepare_llm_inputs_wf4``
  - BERT-BATCH  : ``run_bert_batch_for_papers`` -> ``run_bert_batch_for_papers_wf4`` (max=40)
  - LLM        : ``process_llm_and_post`` -> ``process_llm_and_post_wf4``

The phase structure (PREP -> BERT-BATCH -> LLM), ``self.llm_eid`` /
``self.w1_rule_ids`` derivation from ``spec.metadata``, and
``_write_bert_batch_monitor`` are byte-identical to wf3. ``self.llm_eid`` resolves
to ``WF4_LLM_EXTRACTOR_ID`` via the wf4 spec; ``self.w1_rule_ids`` is
``["rules.conclusion_limitations"]`` (the only non-LLM eid in W1).
"""

from __future__ import annotations

import logging

import json
import os
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from pipeline.benchmark.config import LLM_MODEL
from pipeline.benchmark.stages.llm_client import SingleLLMClient
from pipeline.production.adapters.wf8_stages import LlmPrepared
from pipeline.production.adapters.wf4_stages import (
    prepare_llm_inputs_wf4,
    run_bert_batch_for_papers_wf4,
)
from pipeline.production.test_hooks import barrier as _phase3_barrier
from pipeline.production.batch_llm_common import (
    PaperBatchState,
    PaperJob,
    finalize_errored,
)
from pipeline.production.batch_llm_common_wf4 import process_llm_and_post_wf4
from pipeline.production.config import WF4_MAX_QWEN_SENTENCES
from pipeline.production.context import PaperContext
from pipeline.production.monitor import utc_now
from pipeline.production.post_llm import run_wave_sync
from pipeline.production.registry import ensure_registered
from pipeline.production.workflows.spec import WorkflowSpec

_SENTINEL = object()
_PREP_WORKERS = 4
# End-of-input marker for the global batcher's inbound queue (distinct from the
# LLM worker _SENTINEL): "all PREP producers are done" != "queue is empty".
_END_OF_INPUT = object()


logger = logging.getLogger(__name__)


class BertGlobalBatcher:
    """v0.7 Phase 1: single-flight global BERT batcher.

    Collects prepared papers (submitted by the PREP chunk cadence as soon as
    each chunk finishes) into ONE bounded inbound queue and flushes CROSS-chunk
    groups to a single ``batch_fn`` call when any budget is met:

        max_papers    — group paper count
        max_sentences — sentence-count budget (token-budget approximation)
        max_chars     — char-count safety cap (token-budget approximation)
        max_wait_ms   — oldest pending paper age (latency bound)

    The token budget is degraded to a sentence-count + char-count double
    budget — a DECLARED v0.7 known limitation (no tokenizer dependency; a
    short and an extra-long sentence both count as 1 sentence, chars cap the
    total payload size). A single paper larger than the sentence/char budget
    is still sent alone (never split, never starved).

    Lifecycle protocol:
        producer done -> ``end_of_input()`` puts END sentinel -> loop flushes
        any remainder -> ``run()`` returns (== BERT_DONE). Callers must join
        the batcher thread before draining downstream queues. An in-flight
        ``batch_fn`` call always completes before the loop exits — with
        ``endpoint_concurrency > 1`` this extends to EVERY lane future
        (run() drains outstanding futures and shuts the executor down with
        wait=True before returning).

    TODO-V07-13 lanes (``endpoint_concurrency > 1``):
        flushed batches are submitted to a batcher-owned ThreadPoolExecutor
        (nginx load-balances concurrent requests to N backend instances).
        Invariants preserved: in-flight HTTP is bounded to
        ``endpoint_concurrency`` (the consumer blocks on the OLDEST
        outstanding future before submitting); ``batch_index`` is assigned in
        the consumer thread from a submission counter (monotonic, unique,
        completion-order independent); ``_phase3_barrier("bert_flush")`` fires
        once per batch in the consumer thread; completed stats append to
        ``batches`` under a lock (completion order), and dispatch/error
        callbacks run on the lane thread (all queue-put / lock-protected).
        ``endpoint_concurrency=1`` keeps the Phase 1 single-flight path
        byte-identical (inline call in the consumer thread).

    Error isolation (intentional robustness improvement over chunked mode,
    where a BERT exception aborts the whole window):
        - ``batch_fn`` raising fails ONLY the papers of that batch (via
          ``error_fn``); subsequent batches continue.
        - a 200 response missing a paper_id is NOT silently treated as empty:
          the missing pid is absent from the results dict passed to
          ``dispatch_fn``, and the scheduler marks it errored (paper_id-based
          mapping never depends on response order).
    """

    def __init__(
        self,
        *,
        max_papers: int = 16,
        max_sentences: int = 1500,
        max_chars: int = 300_000,
        max_wait_ms: int = 20,
        batch_fn: Callable[[dict[str, Any]], dict[str, Any]],
        dispatch_fn: Callable[[dict[str, Any], list[str], dict[str, Any]], None] | None = None,
        error_fn: Callable[[list[str], str], None] | None = None,
        batch_index_start: int = 0,
        inbound_maxsize: int | None = None,
        jobs: dict[str, Any] | None = None,
        endpoint_concurrency: int = 1,
    ) -> None:
        self.max_papers = max(1, int(max_papers))
        self.max_sentences = max(1, int(max_sentences))
        self.max_chars = max(1, int(max_chars))
        self.max_wait_ms = float(max_wait_ms)
        self.batch_fn = batch_fn
        self.dispatch_fn = dispatch_fn
        self.error_fn = error_fn
        self.batch_index_start = int(batch_index_start)
        # Scheduler's jobs dict (same injection pattern as _StagedQueue): lets
        # the consumer stamp per-paper timings at flush time. None keeps the
        # batcher usable standalone (tests, direct construction).
        self.jobs = jobs
        # v0.7 TODO-V07-13: >1 lanes run batch_fn HTTP calls on a batcher-owned
        # ThreadPoolExecutor (nginx load-balances to N backend instances).
        # 1 keeps the Phase 1 single-flight behavior byte-identical.
        self.endpoint_concurrency = max(1, int(endpoint_concurrency))
        # Bounded inbound queue (~2 batches of headroom) — a slow batch_fn
        # applies backpressure to PREP instead of growing memory without bound.
        # v0.7 Phase 2: inbound capacity is configurable (staged pipeline's
        # bert_queue_maxsize); default keeps the Phase 1 behavior.
        self.inbound: queue.Queue = queue.Queue(
            maxsize=int(inbound_maxsize) if inbound_maxsize else 2 * self.max_papers
        )
        self.batches: list[dict[str, Any]] = []
        self._seen: set[str] = set()
        # Lane state (dual-lane mode): batch_index is assigned in the consumer
        # thread from a submission counter (monotonic+unique even when lane
        # completions interleave); completed stats append under a lock because
        # lane threads finish out of order.
        self._batch_seq = 0
        self._batches_lock = threading.Lock()
        self._executor: ThreadPoolExecutor | None = None
        self._outstanding: list[Any] = []

    # ------------------------------------------------------------ producers

    @staticmethod
    def _paper_budget(prepared: Any) -> tuple[int, int, int]:
        """(sentence_count, total_chars, max_single_sentence_chars)."""
        sents = list(getattr(prepared, "english_sentences", None) or [])
        return len(sents), sum(len(s) for s in sents), max((len(s) for s in sents), default=0)

    def submit(self, pid: str, prepared: Any) -> None:
        self.inbound.put((pid, prepared, time.perf_counter()))

    def end_of_input(self) -> None:
        self.inbound.put(_END_OF_INPUT)

    # ------------------------------------------------------------ consumer

    def run(self) -> None:
        if self.endpoint_concurrency > 1:
            self._executor = ThreadPoolExecutor(
                max_workers=self.endpoint_concurrency, thread_name_prefix="bert-lane"
            )
        pending: list[tuple[str, Any, float]] = []
        p_sent = 0
        p_chars = 0
        while True:
            timeout = None
            if pending:
                elapsed_ms = (time.perf_counter() - pending[0][2]) * 1000.0
                timeout = max(0.0, (self.max_wait_ms - elapsed_ms) / 1000.0)
            try:
                item = self.inbound.get(timeout=timeout)
            except queue.Empty:
                item = None
            if item is _END_OF_INPUT:
                if pending:
                    self._flush(pending, p_sent, p_chars, "end_of_input")
                if self._executor is not None:
                    # BERT_DONE invariant extended to lanes: run() returns only
                    # after EVERY in-flight lane future completes.
                    for fut in self._outstanding:
                        fut.result()
                    self._executor.shutdown(wait=True)
                return
            if item is None:
                # max_wait_ms elapsed while papers are pending (queue empty but
                # producer NOT done) -> latency flush.
                self._flush(pending, p_sent, p_chars, "max_wait_ms")
                pending, p_sent, p_chars = [], 0, 0
                continue
            pid, prepared, _t_submit = item
            if pid in self._seen:
                if self.error_fn:
                    self.error_fn([pid], f"bert_global_batch: duplicate paper_id {pid}")
                continue
            self._seen.add(pid)
            sents, chars, _ = self._paper_budget(prepared)
            if pending and (
                p_sent + sents > self.max_sentences or p_chars + chars > self.max_chars
            ):
                reason = (
                    "max_sentences" if p_sent + sents > self.max_sentences else "max_chars"
                )
                self._flush(pending, p_sent, p_chars, reason)
                pending, p_sent, p_chars = [], 0, 0
            pending.append((pid, prepared, _t_submit))
            p_sent += sents
            p_chars += chars
            if len(pending) >= self.max_papers:
                self._flush(pending, p_sent, p_chars, "max_papers")
                pending, p_sent, p_chars = [], 0, 0

    def _stamp_bert_queue_wait(self, group: list[tuple[str, Any, float]]) -> None:
        """Per-paper inbound wait: submit (PREP handoff) -> this batch's HTTP
        start, i.e. inbound queue + pending accumulation (under multi-lane,
        also the backpressure wait for a free lane). Called in _run_batch —
        consumer thread OR lane — right before batch_fn, so it stays correct
        when lane completion order interleaves (stamp is completion-independent)."""
        if not self.jobs:
            return
        now = time.perf_counter()
        for pid, _prepared, t_submit in group:
            job = self.jobs.get(pid)
            if job is not None:
                job.timings["bert_queue_wait"] = round(max(0.0, now - t_submit), 4)

    def _flush(
        self,
        group: list[tuple[str, Any, float]],
        p_sent: int,
        p_chars: int,
        reason: str,
    ) -> None:
        prepared_map = {pid: prepared for pid, prepared, _ in group}
        # batch_index: assigned HERE, in the consumer thread, from the
        # submission counter — monotonic and unique under any lane completion
        # order (identical to start+len(batches) in the single-flight case).
        stat: dict[str, Any] = {
            "batch_index": self.batch_index_start + self._batch_seq,
            "paper_ids": [pid for pid, _, _ in group],
            "paper_count": len(group),
            "sentence_count": p_sent,
            "char_count": p_chars,
            "max_sentence_chars": max(
                (self._paper_budget(p)[2] for p in prepared_map.values()), default=0
            ),
            "flush_reason": reason,
            "bert_started_at": utc_now(),
            "bert_client_sec": 0.0,
            "bert_finished_at": utc_now(),
        }
        self._batch_seq += 1
        # Fault-injection hook: called ONCE per batch, always in the consumer
        # thread (deterministic trip order for the kill-restart driver; the
        # hook never raises, so this is equivalent to the Phase 1 placement
        # inside _run_batch's try).
        _phase3_barrier("bert_flush")
        if self._executor is None:
            # single-flight: inline call in the consumer thread (Phase 1 path,
            # behavior unchanged).
            self._run_batch(stat, prepared_map, group)
            return
        # multi-lane: bound in-flight HTTP to endpoint_concurrency by waiting
        # for the OLDEST outstanding future.
        while len(self._outstanding) >= self.endpoint_concurrency:
            self._outstanding.pop(0).result()
        self._outstanding.append(
            self._executor.submit(self._run_batch, stat, prepared_map, group)
        )

    def _run_batch(
        self,
        stat: dict[str, Any],
        prepared_map: dict[str, Any],
        group: list[tuple[str, Any, float]] | None = None,
    ) -> None:
        """One batch_fn HTTP call + result routing (consumer thread OR a lane).

        ``group`` carries the submit perf stamps; the queue-wait stamp is taken
        HERE so bert_queue_wait = submit -> lane HTTP start, which under
        multi-lane includes the backpressure wait for a free lane."""
        if group is not None:
            self._stamp_bert_queue_wait(group)
        t0 = time.perf_counter()
        try:
            results = self.batch_fn(prepared_map) or {}
        except Exception as exc:  # noqa: BLE001 — isolate the failure to this batch
            stat["bert_client_sec"] = round(time.perf_counter() - t0, 4)
            stat["bert_finished_at"] = utc_now()
            stat["error"] = f"{type(exc).__name__}: {exc}"
            with self._batches_lock:
                self.batches.append(stat)
            if self.error_fn:
                self.error_fn(
                    stat["paper_ids"], f"bert_batch_failed: {type(exc).__name__}: {exc}"
                )
            return
        stat["bert_client_sec"] = round(time.perf_counter() - t0, 4)
        stat["bert_finished_at"] = utc_now()
        with self._batches_lock:
            self.batches.append(stat)
        if self.dispatch_fn:
            self.dispatch_fn(results, stat["paper_ids"], stat)


class BatchBertPipelineSchedulerWf4:
    """Cross-paper /filter/batch + LLM pipeline scheduler (wf4)."""

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
        llm_model_tag: str | None = None,
        ollama_format: str | None = None,
        num_predict_override: int | None = None,
        prompt_adapter: str | None = None,
        skip_bert_filter: bool = False,
        nobert_num_ctx: int = 32768,
        nobert_max_prompt_chars: int = 100_000,
        bert_struct: bool = False,
        bert_struct_max_sentences: int = 60,
        bert_struct_num_ctx: int = 8192,
        bert_flat_60: bool = False,
        bert_flat_max_sentences: int = 60,
        bert_flat_num_ctx: int = 8192,
        bert_flat_50: bool = False,
        llm_backend: str = "ollama",  # "ollama" or "openai_chat"
        llm_api_url: str | None = None,  # For openai_chat backend
        llm_model: str | None = None,  # For openai_chat backend (yaml llm_model / env LLM_MODEL)
        llm_timeout: int = 30,  # HTTP timeout for LLM client (yaml llm_timeout)
        bert_server_url: str | None = None,  # Override BERT server URL
        bert_pipeline_batch_size: int = 0,  # 0=legacy global BERT, >0=chunked overlap
        bert_timeout: int | None = None,  # Per-attempt BERT HTTP timeout (s)
        bert_retries: int | None = None,  # Retries on transient BERT network errors
        bert_pipeline_mode: str = "chunked_overlap",  # v0.7: "chunked_overlap" | "global_batch"
        bert_batch_max_papers: int = 16,  # global_batch: flush budget (papers)
        bert_batch_max_sentences: int = 1500,  # global_batch: flush budget (sentences)
        bert_batch_max_chars: int = 300_000,  # global_batch: flush budget (chars)
        bert_batch_max_wait_ms: int = 20,  # global_batch: flush budget (latency)
        bert_endpoint_concurrency: int = 1,  # global_batch: parallel /filter/batch lanes (TODO-V07-13)
        scheduler_mode: str = "default",  # v0.7 Phase 2: "default" | "staged" (runners construct StagedPipelineWf4 for "staged")
        on_paper_done: Callable[[Any], None] | None = None,
        materialize_jobs: bool = True,  # internal: False => rolling staged admits PaperJobs incrementally
    ) -> None:
        ensure_registered()
        if bert_struct and skip_bert_filter:
            raise ValueError(
                "--bert-struct and --skip-bert-filter are mutually exclusive "
                "(bert-struct keeps SciBERT; skip-bert-filter drops it)."
            )
        if bert_flat_50 and (skip_bert_filter or bert_struct or bert_flat_60):
            raise ValueError(
                "--bert-flat-50 is mutually exclusive with --skip-bert-filter, "
                "--bert-struct, and --bert-flat-60 (only one input axis at a time)."
            )
        if bert_flat_60 and (skip_bert_filter or bert_struct or bert_flat_50):
            raise ValueError(
                "--bert-flat-60 is mutually exclusive with --skip-bert-filter "
                "and --bert-struct and --bert-flat-50 (only one input axis at a time)."
            )
        self.paper_ids = list(paper_ids)
        self.md_paths = md_paths
        self.run_id = run_id
        self.spec = spec
        self.llm_concurrency = llm_concurrency
        self.bert_batch_size = bert_batch_size
        # 0/None -> auto (one shot unless large); >0 -> force papers per chunk.
        self.bert_chunk_papers = bert_chunk_papers or None
        self.dry_run = dry_run
        self.llm_model_tag = llm_model_tag
        # Per-model calling-convention overrides (wf4 model-sweep fix).
        self.ollama_format = ollama_format
        self.num_predict_override = num_predict_override
        self.prompt_adapter = prompt_adapter
        # nobert structured-input ablation (--skip-bert-filter). When True, Phase 2
        # builds a marker-structured + cross-block-deduped llm_input from PREP's
        # stashed merged_text instead of calling /filter/batch; papers whose
        # structured prompt exceeds nobert_max_prompt_chars fall back to the BERT
        # path. nobert_num_ctx is the Ollama context window set for nobert papers.
        self.skip_bert_filter = skip_bert_filter
        self.nobert_num_ctx = nobert_num_ctx
        self.nobert_max_prompt_chars = nobert_max_prompt_chars
        # bert-struct-60 structured-input axis (--bert-struct). When True, Phase 2
        # STILL calls SciBERT /filter/batch (unlike skip-bert), but on per-block-
        # washed + cross-block-deduped sentences (markers stripped), re-attaches
        # block membership via the returned indices, selects up to
        # bert_struct_max_sentences (60) preserving block structure, and renders
        # via the structured adapter. bert_struct_num_ctx is the Ollama context
        # window for bert-struct papers (headroom for the larger 60-sentence prompt).
        self.bert_struct = bert_struct
        self.bert_struct_max_sentences = bert_struct_max_sentences
        self.bert_struct_num_ctx = bert_struct_num_ctx
        # bert-flat-60 input axis (--bert-flat-60). When True, the baseline flat
        # path (SciBERT /filter/batch on whole-text english_sentences + V0
        # numbered prompt, NO structure, NO dedup) keeps everything except the
        # sentence cap, raised from 40 to bert_flat_max_sentences (60). Isolates
        # the sentence-cap variable vs bert-flat-40 / bert-struct-60.
        # bert_flat_num_ctx is the Ollama context window (headroom for 60-sentence
        # prompt; baseline flat-40 stays num_ctx=None).
        self.bert_flat_60 = bert_flat_60
        self.bert_flat_50 = bert_flat_50
        self.bert_flat_max_sentences = bert_flat_max_sentences
        self.bert_flat_num_ctx = bert_flat_num_ctx
        # LLM backend: "ollama" (default) or "openai_chat"
        self.llm_backend = llm_backend
        self.llm_api_url = llm_api_url
        # LLM model override (CLI/yaml param > env > benchmark-config default),
        # stored the same way as bert_server_url.
        self.llm_model = llm_model or os.environ.get("LLM_MODEL")
        self.llm_timeout = int(llm_timeout) if llm_timeout else 30
        # BERT server URL override (CLI param > env > default)
        self.bert_server_url = bert_server_url or os.environ.get("BERT_SERVER_URL")
        # Pipeline mode: 0=legacy global BERT, >0=chunked overlap (recommend 10)
        self.bert_pipeline_batch_size = bert_pipeline_batch_size
        # BERT HTTP timeout / retries (None => bert_batch_client defaults apply)
        self.bert_timeout = bert_timeout
        self.bert_retries = bert_retries
        # v0.7 Phase 1: "global_batch" routes PREP output into ONE bounded queue
        # drained by a single-flight BertGlobalBatcher (cross-chunk groups).
        self.bert_pipeline_mode = str(bert_pipeline_mode or "chunked_overlap")
        if self.bert_pipeline_mode not in ("chunked_overlap", "global_batch"):
            raise ValueError(
                f"bert_pipeline_mode must be 'chunked_overlap' or 'global_batch', "
                f"got {self.bert_pipeline_mode!r}"
            )
        self.bert_batch_max_papers = int(bert_batch_max_papers)
        self.bert_batch_max_sentences = int(bert_batch_max_sentences)
        self.bert_batch_max_chars = int(bert_batch_max_chars)
        self.bert_batch_max_wait_ms = int(bert_batch_max_wait_ms)
        self.bert_endpoint_concurrency = max(1, int(bert_endpoint_concurrency))
        # v0.7 Phase 2: scheduling mode. "default" keeps the legacy
        # thread/queue structure (this class's run()); "staged" is only valid
        # on the StagedPipelineWf4 subclass (bounded stage queues + single
        # writer). Recorded here so runners/summaries can mirror one field.
        self.scheduler_mode = str(scheduler_mode or "default")
        if self.scheduler_mode not in ("default", "staged"):
            raise ValueError(
                f"scheduler_mode must be 'default' or 'staged', got {self.scheduler_mode!r}"
            )

        self.llm_eid: str = spec.metadata.get("llm_extractor_id", "llm.wf4_dev20_v2_wash_datasets")
        self.w1_rule_ids: list[str] = [
            eid for eid in spec.waves[0] if eid != self.llm_eid
        ]

        self.llm_q: queue.Queue = queue.Queue()
        # Default: the whole (window) paper set is materialized up front, as
        # before. Rolling staged (TODO-V07-10) passes materialize_jobs=False
        # and creates PaperJobs incrementally in admit_paper() so the jobs
        # dict only ever holds admitted papers.
        self.jobs: dict[str, PaperJob] = (
            {
                pid: PaperJob(paper_id=pid, md_path=md_paths[pid], run_id=run_id, spec=spec, dry_run=dry_run)
                for pid in self.paper_ids
            }
            if materialize_jobs
            else {}
        )
        self._lock = threading.Lock()
        self.batch_monitor: dict[str, Any] | None = None
        self.on_paper_done = on_paper_done

    def _fire_done(self, job: PaperJob) -> None:
        """Live per-paper callback (e.g. progress JSONL). No-op if unset."""
        if self.on_paper_done is not None:
            try:
                self.on_paper_done(job)
            except Exception:  # noqa: BLE001 — progress logging must never break the run
                pass

    def _fail_paper(self, job: PaperJob, *, source: str) -> None:
        """Failure terminal: mark ERROR, write the error prediction, fire done.

        Default (legacy/chunked/global_batch) writes inline. The staged v0.7
        Phase 2 subclass overrides this to route the error finalization
        through its single writer via ``commit_once`` bookkeeping.
        """
        self._set_state(job, PaperBatchState.ERROR)
        finalize_errored(job, spec=self.spec, run_id=self.run_id, dry_run=self.dry_run)
        self._fire_done(job)

    # ------------------------------------------------------------------ run

    def run(self) -> list:
        # Route to global batcher (v0.7 Phase 1), chunked overlap, or legacy global BERT
        if self.bert_pipeline_mode == "global_batch":
            return self._run_global_batch()
        if self.bert_pipeline_batch_size > 0:
            return self._run_chunked_overlap()

        # Legacy path: global PREP → global BERT → LLM pool
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

        # Tag legacy mode in monitor
        if self.batch_monitor is not None:
            self.batch_monitor["pipeline_mode"] = "legacy_global_bert"
        else:
            # Handle case where batch_monitor is None (dry-run or no papers)
            self.batch_monitor = {
                "pipeline_mode": "legacy_global_bert",
            }

        return [self.jobs[pid].result for pid in self.paper_ids]

    # ------------------------------------------------------------------ phases

    def _set_state(self, job: PaperJob, state: PaperBatchState) -> None:
        with self._lock:
            job.state = state

    # ------------------------------------------------------------------ chunked pipeline helpers

    def _chunk_papers(self, paper_ids: list[str], chunk_size: int) -> list[list[str]]:
        """Split paper_ids into chunks of at most chunk_size."""
        return [paper_ids[i : i + chunk_size] for i in range(0, len(paper_ids), chunk_size)]

    def _prep_chunk(self, chunk_ids: list[str]) -> None:
        """PREP all papers in one chunk (similar to _prep_paper but for multiple)."""
        def _prep_one(pid: str) -> None:
            self._prep_paper(pid)

        with ThreadPoolExecutor(max_workers=min(_PREP_WORKERS, len(chunk_ids))) as pool:
            list(pool.map(_prep_one, chunk_ids))

        # Ensure errored papers are finalized (defensive: finalize all ERROR papers)
        from pipeline.production.batch_llm_common import finalize_errored
        for pid in chunk_ids:
            job = self.jobs[pid]
            if job.state == PaperBatchState.ERROR and job.result is None:
                finalize_errored(job, spec=self.spec, run_id=self.run_id, dry_run=self.dry_run)
                self._fire_done(job)

    def _run_bert_chunk(
        self, chunk_index: int, chunk_ids: list[str], prep_wait_sec: float = 0.0
    ) -> dict[str, Any]:
        """Run BERT batch for one chunk (subset of _run_bert_batch).

        Args:
            chunk_index: Current chunk index (0-indexed)
            chunk_ids: Paper IDs in this chunk
            prep_wait_sec: Time waited for PREP to complete (for observability)

        Returns:
            Chunk statistics dict with prepared_count, missing_prep_count, prep_wait_sec
        """
        from pipeline.production.batch_llm_common import finalize_errored
        from pipeline.production.config import WF4_MAX_QWEN_SENTENCES

        prepared_map: dict[str, LlmPrepared] = {
            pid: self.jobs[pid].prepared
            for pid in chunk_ids
            if self.jobs[pid].prepared is not None
        }

        chunk_stat: dict[str, Any] = {
            "chunk_index": chunk_index,
            "paper_ids": chunk_ids,
            "paper_count": len(chunk_ids),
            "prepared_count": len(prepared_map),
            "missing_prep_count": len(chunk_ids) - len(prepared_map),
            "prep_sec": 0.0,
            "prep_wait_sec": prep_wait_sec,
            "bert_client_sec": 0.0,
            "bert_started_at": utc_now(),
            "bert_finished_at": utc_now(),
        }

        # Critical: Do NOT enqueue papers when prepared_map is empty (not dry_run)
        # This prevents the race condition where bert_result is None → AttributeError
        if not prepared_map and not self.dry_run:
            logger.warning(
                f"Chunk {chunk_index}: prepared_map empty, "
                f"not dry_run, cannot enqueue to LLM (would cause AttributeError)"
            )
            bert_done_perf = time.perf_counter()
            chunk_stat["bert_finished_at"] = utc_now()
            for pid in chunk_ids:
                job = self.jobs[pid]
                if job.state == PaperBatchState.ERROR:
                    continue
                # Mark as errored with specific error
                job.error = (
                    f"bert_chunk_{chunk_index}: prep not ready, prepared_map empty, "
                    f"cannot build llm_input"
                )
                job.timings["bert_mode"] = "batch"
                job.timings["bert_elapsed_sec"] = 0.0
                job.timings["bert_batch_chunk"] = chunk_index
                job.timings["_bert_done_perf"] = bert_done_perf
                job.timings["llm_queued_at"] = utc_now()
                self._set_state(job, PaperBatchState.ERROR)
                finalize_errored(job, spec=self.spec, run_id=self.run_id, dry_run=False)
                self._fire_done(job)
            return chunk_stat

        # Dry-run: mark bert done, enqueue for LLM (stub mode, LLM handles stub bert_result)
        if self.dry_run:
            bert_done_perf = time.perf_counter()
            chunk_stat["bert_finished_at"] = utc_now()
            for pid in chunk_ids:
                job = self.jobs[pid]
                if job.state == PaperBatchState.ERROR:
                    continue
                job.timings["bert_mode"] = "stub"
                job.timings["bert_elapsed_sec"] = 0.0
                job.timings["bert_batch_chunk"] = chunk_index
                job.timings["_bert_done_perf"] = bert_done_perf
                job.timings["llm_queued_at"] = utc_now()
                if self.bert_flat_60 or self.bert_flat_50:
                    job.timings["input_path"] = "bert_flat"
                    job.timings["num_ctx"] = self.bert_flat_num_ctx
                    job.timings["max_llm_sentences"] = self.bert_flat_max_sentences
                self._set_state(job, PaperBatchState.LLM_QUEUED)
                self.llm_q.put(pid)
            return chunk_stat

        flat_max = (
            self.bert_flat_max_sentences
            if self.bert_flat_60 or self.bert_flat_50
            else WF4_MAX_QWEN_SENTENCES
        )

        t = time.perf_counter()
        results, _ = run_bert_batch_for_papers_wf4(
            prepared_map,
            max_sentences=flat_max,
            chunk_max_papers=None,  # chunking handled by caller
            batch_size=self.bert_batch_size,
            bert_server_url=self.bert_server_url,
            bert_timeout=self.bert_timeout,
            bert_retries=self.bert_retries,
        )
        chunk_stat["bert_client_sec"] = round(time.perf_counter() - t, 4)
        chunk_stat["bert_finished_at"] = utc_now()
        bert_done_perf = time.perf_counter()

        for pid in chunk_ids:
            job = self.jobs[pid]
            if job.state == PaperBatchState.ERROR:
                continue
            bert_res = results.get(pid)
            if bert_res is None:
                job.error = f"bert_chunk_{chunk_index}: no result for paper"
                self._set_state(job, PaperBatchState.ERROR)
                finalize_errored(job, spec=self.spec, run_id=self.run_id, dry_run=False)
                self._fire_done(job)
                continue
            job.bert_result = bert_res
            job.timings["bert_mode"] = "batch"
            job.timings["bert_batch_chunk"] = chunk_index
            job.timings["bert_amortized_sec"] = bert_res.timings.get("bert_amortized_sec", 0.0)
            job.timings["_bert_done_perf"] = bert_done_perf
            job.timings["llm_queued_at"] = utc_now()
            if self.bert_flat_60 or self.bert_flat_50:
                job.timings["input_path"] = "bert_flat"
                job.timings["num_ctx"] = self.bert_flat_num_ctx
                job.timings["max_llm_sentences"] = self.bert_flat_max_sentences
            self._set_state(job, PaperBatchState.LLM_QUEUED)
            self.llm_q.put(pid)

        return chunk_stat

    def _run_chunked_overlap(self) -> list:
        """Run pipeline with chunked BERT overlapping LLM processing."""
        import logging

        logger = logging.getLogger(__name__)

        chunks = self._chunk_papers(self.paper_ids, self.bert_pipeline_batch_size)
        # Cross-window chunk_index continuity (multi-window runs share run_id):
        # same mechanism as the global batcher's batch_index_start.
        chunk_base = self._existing_chunked_chunk_count()
        chunk_stats: list[dict[str, Any]] = []

        # Phase 1: PREP first chunk (must complete before BERT)
        t_prep = time.perf_counter()
        self._prep_chunk(chunks[0])
        logger.debug(f"Chunk 0 PREP completed in {round(time.perf_counter() - t_prep, 4)}s")

        # Start LLM workers early
        llm_workers = [
            threading.Thread(target=self._qwen_worker, name=f"llm-{i}", daemon=True)
            for i in range(self.llm_concurrency)
        ]
        for w in llm_workers:
            w.start()

        # Phase 2-3: Pipeline loop
        next_chunk_idx = 1
        prep_threads: list[threading.Thread] = [None] * len(chunks)
        # chunk 0 already PREP'd (synchronous)

        for chunk_idx, chunk_ids in enumerate(chunks):
            # Wait for this chunk's PREP to complete before BERT (fix: no PREP → BERT race)
            if prep_threads[chunk_idx] is not None:
                prep_start_wait = time.perf_counter()
                prep_threads[chunk_idx].join()
                prep_wait_sec = round(time.perf_counter() - prep_start_wait, 4)
                logger.debug(f"Chunk {chunk_idx} PREP wait: {prep_wait_sec}s")
            elif chunk_idx == 0:
                # chunk 0 already PREP'd synchronously
                prep_wait_sec = 0.0
            else:
                # Should not happen: chunk 1+ should have prep_thread
                logger.warning(f"Chunk {chunk_idx} has no prep_thread, assuming already PREP'd")
                prep_wait_sec = 0.0

            # BERT phase for current chunk
            chunk_stat = self._run_bert_chunk(
                chunk_base + chunk_idx, chunk_ids, prep_wait_sec=prep_wait_sec
            )
            chunk_stats.append(chunk_stat)
            logger.debug(
                f"Chunk {chunk_idx} BERT completed in {chunk_stat['bert_client_sec']}s, "
                f"papers queued: {chunk_stat['prepared_count']}/{chunk_stat['paper_count']}"
            )

            # Trigger PREP for next chunk (if exists) in background
            if next_chunk_idx < len(chunks):
                next_chunk_ids = chunks[next_chunk_idx]
                prep_threads[next_chunk_idx] = threading.Thread(
                    target=self._prep_chunk,
                    args=(next_chunk_ids,),
                    name=f"prep-chunk-{next_chunk_idx}",
                    daemon=True,
                )
                prep_threads[next_chunk_idx].start()
                next_chunk_idx += 1

        # Shutdown LLM workers
        for _ in range(self.llm_concurrency):
            self.llm_q.put(_SENTINEL)
        for w in llm_workers:
            w.join()

        # Build chunk monitor
        sum_bert_sec = sum(c.get("bert_client_sec", 0.0) for c in chunk_stats)
        self.batch_monitor = {
            "pipeline_mode": "chunked_overlap",
            "chunks": chunk_stats,
            "chunk_count": len(chunks),
            "bert_pipeline_batch_size": self.bert_pipeline_batch_size,
            "sum_chunk_bert_sec": round(sum_bert_sec, 4),
        }
        self._write_chunked_batch_monitor(self.batch_monitor)

        # Defensive: ensure all papers have results (finalize any that don't)
        from pipeline.production.batch_llm_common import finalize_errored
        for pid in self.paper_ids:
            job = self.jobs[pid]
            if job.result is None:
                logger.warning(f"Paper {pid} has no result after pipeline run, finalizing as errored")
                if job.error is None:
                    job.error = "no_result_set"
                finalize_errored(job, spec=self.spec, run_id=self.run_id, dry_run=self.dry_run)
                self._fire_done(job)

        return [self.jobs[pid].result for pid in self.paper_ids]

    # ------------------------------------------------------------ global batch (v0.7 Phase 1)

    def _flat_max_sentences(self) -> int:
        """LLM sentence cap for the flat BERT path (wf4 default 60)."""
        if self.bert_flat_60 or self.bert_flat_50:
            return self.bert_flat_max_sentences
        return WF4_MAX_QWEN_SENTENCES

    def _submit_to_batcher(self, batcher: BertGlobalBatcher, pid: str) -> None:
        """Hand one PREP'd paper to the global batcher (or finalize early)."""
        job = self.jobs[pid]
        if job.state == PaperBatchState.ERROR:
            return  # prep already finalized it
        if job.prepared is None:
            if self.dry_run:
                # Mirror chunked dry-run: stub bert, enqueue for LLM directly.
                job.timings["bert_mode"] = "stub"
                job.timings["bert_elapsed_sec"] = 0.0
                job.timings["_bert_done_perf"] = time.perf_counter()
                job.timings["llm_queued_at"] = utc_now()
                self._set_state(job, PaperBatchState.LLM_QUEUED)
                self.llm_q.put(pid)
            else:
                job.error = "bert_global_batch: prep not ready (prepared is None)"
                job.timings["bert_mode"] = "batch"
                job.timings["bert_elapsed_sec"] = 0.0
                self._fail_paper(job, source="bert_prep_not_ready")
            return
        batcher.submit(pid, job.prepared)

    def _global_batch_fn(self, prepared_map: dict[str, LlmPrepared]) -> dict[str, Any]:
        """One /filter/batch for a batcher-formed group (single HTTP call).

        ``chunk_max_papers=len(group)`` forces one shot: grouping is the
        batcher's job, and every downstream mapping/assembly line is the SAME
        code path as chunked mode (parity by shared implementation path,
        validated by explicit fixture parity tests — not a proof by itself).
        """
        results, _ = run_bert_batch_for_papers_wf4(
            prepared_map,
            max_sentences=self._flat_max_sentences(),
            chunk_max_papers=max(len(prepared_map), 1),
            batch_size=self.bert_batch_size,
            bert_server_url=self.bert_server_url,
            bert_timeout=self.bert_timeout,
            bert_retries=self.bert_retries,
        )
        return results

    def _global_dispatch(
        self, results: dict[str, Any], group_pids: list[str], stat: dict[str, Any]
    ) -> None:
        """Post-BERT dispatch for one flushed group (mirror of chunked loop)."""
        bert_done_perf = time.perf_counter()
        for pid in group_pids:
            job = self.jobs[pid]
            if job.state == PaperBatchState.ERROR:
                continue
            bert_res = results.get(pid)
            if bert_res is None:
                # HTTP 200 but this paper_id missing from the response: explicit
                # error (never a silent empty result); returned papers proceed.
                job.error = (
                    f"bert_global_batch: no result for paper (batch {stat['batch_index']})"
                )
                self._fail_paper(job, source="bert_missing_paper")
                continue
            job.bert_result = bert_res
            job.timings["bert_mode"] = "batch"
            job.timings["bert_batch_chunk"] = stat["batch_index"]
            job.timings["bert_global_batch_index"] = stat["batch_index"]
            job.timings["bert_amortized_sec"] = bert_res.timings.get("bert_amortized_sec", 0.0)
            job.timings["_bert_done_perf"] = bert_done_perf
            job.timings["llm_queued_at"] = utc_now()
            if self.bert_flat_60 or self.bert_flat_50:
                job.timings["input_path"] = "bert_flat"
                job.timings["num_ctx"] = self.bert_flat_num_ctx
                job.timings["max_llm_sentences"] = self.bert_flat_max_sentences
            self._set_state(job, PaperBatchState.LLM_QUEUED)
            self.llm_q.put(pid)

    def _global_batch_error(self, group_pids: list[str], err: str) -> None:
        """Fail ONLY the papers of a failed batch (intentional robustness
        improvement over chunked mode, where the exception aborts the whole
        window). The persisted error string keeps the paper retryable on
        resume (prediction_ok = not pred.get("error"))."""
        for pid in group_pids:
            job = self.jobs[pid]
            if job.state == PaperBatchState.ERROR:
                continue
            job.error = err
            job.timings["bert_mode"] = "batch"
            job.timings["bert_elapsed_sec"] = 0.0
            job.timings["bert_batch_failed"] = True
            self._fail_paper(job, source="bert_batch_failed")

    def _run_global_batch(self) -> list:
        """v0.7 Phase 1: PREP chunk cadence feeds ONE single-flight batcher.

        PREP keeps the chunked_overlap cadence (chunk N+1 preps while BERT
        runs), but finished chunks are SUBMITTED to the global batcher instead
        of running BERT inline per chunk — groups can span chunk boundaries.
        """
        prep_chunk_size = self.bert_pipeline_batch_size or 10
        chunks = self._chunk_papers(self.paper_ids, prep_chunk_size)

        llm_workers = [
            threading.Thread(target=self._qwen_worker, name=f"llm-{i}", daemon=True)
            for i in range(self.llm_concurrency)
        ]
        for w in llm_workers:
            w.start()

        batcher = BertGlobalBatcher(
            max_papers=self.bert_batch_max_papers,
            max_sentences=self.bert_batch_max_sentences,
            max_chars=self.bert_batch_max_chars,
            max_wait_ms=self.bert_batch_max_wait_ms,
            batch_fn=self._global_batch_fn,
            dispatch_fn=self._global_dispatch,
            error_fn=self._global_batch_error,
            batch_index_start=self._existing_global_batch_count(),
            jobs=self.jobs,
            endpoint_concurrency=self.bert_endpoint_concurrency,
        )
        batcher_thread = threading.Thread(
            target=batcher.run, name="bert-global-batcher", daemon=True
        )
        batcher_thread.start()

        if chunks:
            self._prep_chunk(chunks[0])
        prep_threads: list[threading.Thread | None] = [None] * len(chunks)
        next_chunk_idx = 1
        for chunk_idx, chunk_ids in enumerate(chunks):
            if prep_threads[chunk_idx] is not None:
                prep_threads[chunk_idx].join()
            for pid in chunk_ids:
                self._submit_to_batcher(batcher, pid)
            if next_chunk_idx < len(chunks):
                prep_threads[next_chunk_idx] = threading.Thread(
                    target=self._prep_chunk,
                    args=(chunks[next_chunk_idx],),
                    name=f"prep-chunk-{next_chunk_idx}",
                    daemon=True,
                )
                prep_threads[next_chunk_idx].start()
                next_chunk_idx += 1

        # End of input -> batcher flushes its remainder -> run() returns
        # (BERT_DONE). Only then do we drain LLM.
        batcher.end_of_input()
        batcher_thread.join()

        for _ in range(self.llm_concurrency):
            self.llm_q.put(_SENTINEL)
        for w in llm_workers:
            w.join()

        self.batch_monitor = {
            "pipeline_mode": "global_batch",
            "batches": batcher.batches,
            "batch_count": len(batcher.batches),
            "prep_chunk_size": prep_chunk_size,
            "bert_batch_max_papers": self.bert_batch_max_papers,
            "bert_batch_max_sentences": self.bert_batch_max_sentences,
            "bert_batch_max_chars": self.bert_batch_max_chars,
            "bert_batch_max_wait_ms": self.bert_batch_max_wait_ms,
            "bert_endpoint_concurrency": self.bert_endpoint_concurrency,
            "sum_batch_bert_sec": round(
                sum(b.get("bert_client_sec", 0.0) for b in batcher.batches), 4
            ),
        }
        self._write_global_batch_monitor(self.batch_monitor)

        # Defensive: ensure all papers have results (same contract as chunked).
        for pid in self.paper_ids:
            job = self.jobs[pid]
            if job.result is None:
                logger.warning(f"Paper {pid} has no result after pipeline run, finalizing as errored")
                if job.error is None:
                    job.error = "no_result_set"
                finalize_errored(job, spec=self.spec, run_id=self.run_id, dry_run=self.dry_run)
                self._fire_done(job)

        return [self.jobs[pid].result for pid in self.paper_ids]

    def _existing_global_batch_count(self) -> int:
        """Batches already on disk for this run_id (multi-window append)."""
        from pipeline.production.config import RUNS_DIR

        path = RUNS_DIR / self.run_id / "bert_batch_monitor.json"
        if not path.is_file():
            return 0
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return 0
        if d.get("run_id") == self.run_id and d.get("pipeline_mode") == "global_batch":
            return len(d.get("batches") or [])
        return 0

    def _write_global_batch_monitor(self, monitor: dict[str, Any]) -> None:
        """Append-per-window writer (chunked mode overwrites; global accumulates
        across the scheduler.run() calls run_bulk makes per window)."""
        from pipeline.production.config import RUNS_DIR

        run_dir = RUNS_DIR / self.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / "bert_batch_monitor.json"
        merged = dict(monitor)
        existing_count = self._existing_global_batch_count()
        if existing_count:
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
                merged["batches"] = (d.get("batches") or []) + list(monitor["batches"])
                merged["batch_count"] = len(merged["batches"])
                merged["window_count"] = int(d.get("window_count") or 1) + 1
            except Exception:
                merged["window_count"] = 1
        else:
            merged["window_count"] = 1
        merged["last_window_at"] = utc_now()
        payload = {"run_id": self.run_id, "workflow_id": self.spec.workflow_id, **merged}
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    def _existing_chunked_chunk_count(self) -> int:
        """Chunks already on disk for this run_id (multi-window append)."""
        from pipeline.production.config import RUNS_DIR

        path = RUNS_DIR / self.run_id / "bert_batch_monitor.json"
        if not path.is_file():
            return 0
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return 0
        if d.get("run_id") == self.run_id and d.get("pipeline_mode") == "chunked_overlap":
            return len(d.get("chunks") or [])
        return 0

    def _write_chunked_batch_monitor(self, monitor: dict[str, Any]) -> None:
        """Append-per-window writer for chunked mode (mirror of
        ``_write_global_batch_monitor``): run_bulk calls scheduler.run() once
        per window with the same run_id, so the file accumulates chunks across
        windows. chunk_index continuity is produced at the source
        (``_run_chunked_overlap`` offsets by ``_existing_chunked_chunk_count``),
        the same mechanism as the global batcher's ``batch_index_start``."""
        from pipeline.production.config import RUNS_DIR

        run_dir = RUNS_DIR / self.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / "bert_batch_monitor.json"
        merged = dict(monitor)
        existing_count = self._existing_chunked_chunk_count()
        if existing_count:
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
                merged["chunks"] = (d.get("chunks") or []) + list(monitor["chunks"])
                merged["chunk_count"] = len(merged["chunks"])
                merged["sum_chunk_bert_sec"] = round(
                    float(d.get("sum_chunk_bert_sec") or 0.0)
                    + float(monitor.get("sum_chunk_bert_sec") or 0.0),
                    4,
                )
                merged["window_count"] = int(d.get("window_count") or 1) + 1
            except Exception:
                merged["window_count"] = 1
        else:
            merged["window_count"] = 1
        merged["last_window_at"] = utc_now()
        payload = {"run_id": self.run_id, "workflow_id": self.spec.workflow_id, **merged}
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    def _prep_paper(self, paper_id: str) -> None:
        """Phase 1: read md + meta + W1-rules + Stage-P prepare_llm_inputs_wf4."""
        job = self.jobs[paper_id]
        job.paper_start_perf = time.perf_counter()
        # Paper entry timestamp (PREP start): the top-level monitor "started_at"
        # is the first POST wave's start (waves_log[0]) — a different, later
        # instant. Stamped before the try so md-fetch failures carry it too.
        job.timings["pipeline_started_at"] = utc_now()
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
                job.prepared = prepare_llm_inputs_wf4(job.md_path)
            job.timings["w1_rules_elapsed_sec"] = round(time.perf_counter() - job.paper_start_perf, 4)
            job.timings["prep_elapsed_sec"] = round(time.perf_counter() - prep_start, 4)
        except Exception as exc:  # noqa: BLE001
            job.error = f"prep: {type(exc).__name__}: {exc}"
            self._fail_paper(job, source="prep")

    def _run_bert_batch(self) -> None:
        """Phase 2: one /filter/batch across all prepared papers (wf4, max=40)."""
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

        if self.skip_bert_filter:
            self._run_nobert_struct_batch(prepared_map)
            return

        if self.bert_struct:
            self._run_bert_struct_batch(prepared_map)
            return

        batch_started = utc_now()
        flat_max = (
            self.bert_flat_max_sentences
            if self.bert_flat_60 or self.bert_flat_50
            else WF4_MAX_QWEN_SENTENCES
        )
        results, batch_monitor = run_bert_batch_for_papers_wf4(
            prepared_map,
            max_sentences=flat_max,
            chunk_max_papers=self.bert_chunk_papers,
            batch_size=self.bert_batch_size,
            bert_server_url=self.bert_server_url,
            bert_timeout=self.bert_timeout,
            bert_retries=self.bert_retries,
        )
        batch_done_perf = time.perf_counter()
        if self.bert_flat_60 or self.bert_flat_50:
            batch_monitor["mode"] = "bert_flat"
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
                self._fire_done(job)
                continue
            job.bert_result = bert_res
            job.timings["bert_mode"] = "batch"
            job.timings["bert_batch_chunk"] = bert_res.timings.get("bert_batch_chunk", 0)
            job.timings["bert_amortized_sec"] = bert_res.timings.get("bert_amortized_sec", 0.0)
            job.timings["bert_elapsed_sec"] = 0.0
            if self.bert_flat_60 or self.bert_flat_50:
                # bert-flat-50/60: same flat V0 path, only cap raised + larger ctx.
                # prompt_adapter stays unset => None => V0 numbered prompt.
                job.timings["input_path"] = "bert_flat"
                job.timings["num_ctx"] = self.bert_flat_num_ctx
                job.timings["max_llm_sentences"] = self.bert_flat_max_sentences
            job.timings["_bert_done_perf"] = batch_done_perf
            job.timings["llm_queued_at"] = utc_now()
            self._set_state(job, PaperBatchState.LLM_QUEUED)
            self.llm_q.put(pid)

    def _run_nobert_struct_batch(self, prepared_map: dict[str, LlmPrepared]) -> None:
        """Phase 2 (skip-bert): structured llm_input per paper; overflow -> BERT fallback.

        For each prepared paper, build the nobert structured candidate
        (``run_nobert_stage_wf4``). If its prompt fits ``nobert_max_prompt_chars``
        the paper takes the nobert path (structured adapter + large num_ctx, no
        SciBERT). Overflow papers are collected and run through one
        ``/filter/batch`` (the existing BERT path, V0 + 40-sentence cap) as
        fallback; if the BERT service is unreachable, those papers finalize as
        errored with ``nobert_overflow_bert_unavailable``.
        """
        from pipeline.production.adapters.wf4_stages import run_nobert_stage_wf4
        from pipeline.production.config import WF4_MAX_QWEN_SENTENCES

        nobert_pids: list[str] = []
        fallback_pids: list[str] = []
        per_paper_stats: list[dict[str, Any]] = []
        batch_done_perf = time.perf_counter()

        for pid in self.paper_ids:
            job = self.jobs[pid]
            if job.state == PaperBatchState.ERROR or pid not in prepared_map:
                continue
            try:
                nobert_res = run_nobert_stage_wf4(
                    prepared_map[pid], max_prompt_chars=self.nobert_max_prompt_chars
                )
            except Exception as exc:  # noqa: BLE001
                job.error = f"nobert_struct: {type(exc).__name__}: {exc}"
                self._set_state(job, PaperBatchState.ERROR)
                finalize_errored(job, spec=self.spec, run_id=self.run_id, dry_run=self.dry_run)
                self._fire_done(job)
                continue

            prompt_chars = nobert_res.bert_raw.get("prompt_chars", 0)
            sel = nobert_res.sentence_selection or {}
            if nobert_res.bert_raw.get("overflow"):
                fallback_pids.append(pid)
                per_paper_stats.append({
                    "paper_id": pid, "overflow": True, "prompt_chars": prompt_chars,
                })
                continue

            # nobert path: structured adapter + large num_ctx, BERT skipped.
            job.bert_result = nobert_res
            job.timings["bert_mode"] = "skipped_struct"
            job.timings["bert_elapsed_sec"] = 0.0
            job.timings["prompt_adapter"] = "structured"
            job.timings["num_ctx"] = self.nobert_num_ctx
            job.timings["input_path"] = "nobert_struct"
            job.timings["nobert_prompt_chars"] = prompt_chars
            job.timings["dedup_removed_count"] = sel.get("dedup_removed_count")
            job.timings["input_sentence_count_pre_dedup"] = sel.get("input_sentence_count_pre_dedup")
            job.timings["input_sentence_count_post_dedup"] = sel.get("input_sentence_count_post_dedup")
            job.timings["_bert_done_perf"] = batch_done_perf
            job.timings["llm_queued_at"] = utc_now()
            self._set_state(job, PaperBatchState.LLM_QUEUED)
            self.llm_q.put(pid)
            nobert_pids.append(pid)
            per_paper_stats.append({
                "paper_id": pid, "overflow": False, "prompt_chars": prompt_chars,
                "dedup_removed_count": sel.get("dedup_removed_count"),
            })

        # Overflow papers: fall back to the BERT path (V0 + 40-sentence cap).
        if fallback_pids:
            fb_prepared = {pid: prepared_map[pid] for pid in fallback_pids}
            try:
                results, bert_monitor = run_bert_batch_for_papers_wf4(
                    fb_prepared,
                    chunk_max_papers=self.bert_chunk_papers,
                    batch_size=self.bert_batch_size,
                    bert_server_url=self.bert_server_url,
                    bert_timeout=self.bert_timeout,
                    bert_retries=self.bert_retries,
                )
            except Exception as exc:  # noqa: BLE001 — BERT service unreachable
                results = {}
                bert_monitor = {"error": f"nobert_overflow_bert_unavailable: {type(exc).__name__}: {exc}"}
                for pid in fallback_pids:
                    job = self.jobs[pid]
                    job.error = f"nobert_overflow_bert_unavailable: {type(exc).__name__}: {exc}"
                    self._set_state(job, PaperBatchState.ERROR)
                    finalize_errored(job, spec=self.spec, run_id=self.run_id, dry_run=self.dry_run)
                    self._fire_done(job)
            else:
                self._write_bert_batch_monitor(bert_monitor)
            for pid in fallback_pids:
                job = self.jobs[pid]
                if job.state == PaperBatchState.ERROR:
                    continue
                bert_res = results.get(pid)
                if bert_res is None:
                    job.error = "bert_batch: no result for paper (nobert fallback)"
                    self._set_state(job, PaperBatchState.ERROR)
                    finalize_errored(job, spec=self.spec, run_id=self.run_id, dry_run=self.dry_run)
                    self._fire_done(job)
                    continue
                job.bert_result = bert_res
                job.timings["bert_mode"] = "batch"
                job.timings["bert_batch_chunk"] = bert_res.timings.get("bert_batch_chunk", 0)
                job.timings["bert_amortized_sec"] = bert_res.timings.get("bert_amortized_sec", 0.0)
                job.timings["bert_elapsed_sec"] = 0.0
                # fallback papers use the baseline V0 prompt (no num_ctx override).
                job.timings["prompt_adapter"] = None
                job.timings["num_ctx"] = None
                job.timings["input_path"] = "bert_fallback"
                job.timings["_bert_done_perf"] = batch_done_perf
                job.timings["llm_queued_at"] = utc_now()
                self._set_state(job, PaperBatchState.LLM_QUEUED)
                self.llm_q.put(pid)

        dedup_counts = [
            s["dedup_removed_count"] for s in per_paper_stats
            if s.get("dedup_removed_count") is not None
        ]
        self.batch_monitor = {
            "mode": "nobert_struct",
            "nobert_struct_count": len(nobert_pids),
            "bert_fallback_count": len(fallback_pids),
            "avg_dedup_removed_count": (
                round(sum(dedup_counts) / len(dedup_counts), 4) if dedup_counts else 0
            ),
            "total_prompt_chars": sum(s.get("prompt_chars", 0) for s in per_paper_stats),
            "max_llm_sentences": WF4_MAX_QWEN_SENTENCES,  # informational: fallback cap
            "per_paper": per_paper_stats,
        }

    def _run_bert_struct_batch(self, prepared_map: dict[str, LlmPrepared]) -> None:
        """Phase 2 (bert-struct-60): SciBERT /filter/batch + structured block re-group.

        Per paper, build block-structured + cross-block-deduped sentences from
        PREP's stashed merged_text (split-by-marker, wash, dedup). Send the flat
        deduped sentences to one /filter/batch (chunked), re-attach block
        membership via the returned ``indices``, select up to
        ``bert_struct_max_sentences`` (60) preserving block structure, and
        render via the structured adapter. SciBERT IS called (bert_mode="batch").
        """
        from pipeline.production.adapters.wf4_stages import (
            run_bert_struct_batch_for_papers_wf4,
        )

        results, batch_monitor = run_bert_struct_batch_for_papers_wf4(
            prepared_map,
            max_sentences=self.bert_struct_max_sentences,
            chunk_max_papers=self.bert_chunk_papers,
            batch_size=self.bert_batch_size,
            bert_server_url=self.bert_server_url,
            bert_timeout=self.bert_timeout,
            bert_retries=self.bert_retries,
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
                job.error = "bert_struct_batch: no result for paper"
                self._set_state(job, PaperBatchState.ERROR)
                finalize_errored(job, spec=self.spec, run_id=self.run_id, dry_run=self.dry_run)
                self._fire_done(job)
                continue
            job.bert_result = bert_res
            sel = bert_res.sentence_selection or {}
            job.timings["bert_mode"] = "batch"
            job.timings["bert_batch_chunk"] = bert_res.timings.get("bert_batch_chunk", 0)
            job.timings["bert_amortized_sec"] = bert_res.timings.get("bert_amortized_sec", 0.0)
            job.timings["bert_elapsed_sec"] = 0.0
            job.timings["prompt_adapter"] = "structured"
            job.timings["num_ctx"] = self.bert_struct_num_ctx
            job.timings["input_path"] = "bert_struct"
            job.timings["bert_struct_prompt_chars"] = sel.get("bert_struct_prompt_chars")
            job.timings["dedup_removed_count"] = sel.get("dedup_removed_count")
            job.timings["input_sentence_count_pre_dedup"] = sel.get("input_sentence_count_pre_dedup")
            job.timings["input_sentence_count_post_dedup"] = sel.get("input_sentence_count_post_dedup")
            job.timings["selected_by_block"] = sel.get("selected_by_block")
            job.timings["max_llm_sentences"] = sel.get("max_llm_sentences")
            job.timings["_bert_done_perf"] = batch_done_perf
            job.timings["llm_queued_at"] = utc_now()
            self._set_state(job, PaperBatchState.LLM_QUEUED)
            self.llm_q.put(pid)

    def _make_qwen_client(self) -> Any:
        """Factory: Ollama or OpenAI chat client based on llm_backend."""
        if self.dry_run:
            return None
        if self.llm_backend == "openai_chat":
            from pipeline.benchmark.stages.openai_chat_llm_client import OpenAIChatLLMClient
            # 3-level fallback: explicit arg → env → empty (must be configured
            # via configs/default.yaml or LLM_CHAT_URL; no built-in endpoint).
            api_url = (
                self.llm_api_url or
                os.environ.get("LLM_CHAT_URL") or
                ""
            )
            # Same 3-level fallback as api_url; do NOT pass self.llm_model_tag here
            # (that is an Ollama-side name, meaningless to the vLLM backends).
            model = self.llm_model or LLM_MODEL
            return OpenAIChatLLMClient(
                api_url=api_url,
                timeout=self.llm_timeout,
                default_model=model,
            )
        # Default: Ollama
        return SingleLLMClient(
            default_model=self.llm_model_tag,
            timeout=self.llm_timeout,
        )

    def _qwen_worker(self) -> None:
        """Phase 3: Stage-B (wf4) + glue + POST_LLM + finalize (shared)."""
        llm_client = self._make_qwen_client()
        while True:
            paper_id = self.llm_q.get()
            if paper_id is _SENTINEL:
                return
            job = self.jobs[paper_id]
            # bert_mode: per-paper under skip-bert (skipped_struct | batch);
            # otherwise the legacy batch/serial default (preserves baseline + dry-run).
            if self.skip_bert_filter:
                bert_mode = job.timings.get("bert_mode", "batch")
            else:
                bert_mode = "batch" if not self.dry_run else "serial"
            process_llm_and_post_wf4(
                job,
                spec=self.spec,
                llm_client=llm_client,
                run_id=self.run_id,
                dry_run=self.dry_run,
                bert_mode=bert_mode,
                lock=self._lock,
                llm_model_tag=self.llm_model_tag,
                ollama_format=self.ollama_format,
                num_predict_override=self.num_predict_override,
                prompt_adapter=job.timings.get("prompt_adapter", self.prompt_adapter),
                num_ctx_override=job.timings.get("num_ctx"),
                input_path=job.timings.get("input_path"),
            )
            self._fire_done(job)

    # ------------------------------------------------------------------ monitor

    def _write_bert_batch_monitor(self, batch_monitor: dict[str, Any]) -> None:
        """Whole-file overwrite writer — legacy single-shot axes only
        (``_run_bert_batch`` / ``_run_nobert_struct_batch`` /
        ``_run_bert_struct_batch``). Production multi-window modes use the
        append-per-window writers: ``_write_chunked_batch_monitor`` (chunked)
        and ``_write_global_batch_monitor`` (global_batch / staged)."""
        from pipeline.production.config import RUNS_DIR

        run_dir = RUNS_DIR / self.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        payload = {"run_id": self.run_id, "workflow_id": self.spec.workflow_id, **batch_monitor}
        (run_dir / "bert_batch_monitor.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
