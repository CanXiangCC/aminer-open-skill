"""v0.7 Phase 2: staged (stage-decoupled) production pipeline — TODO-V07-03.

Replaces the Phase 1 scheduling (PREP chunks -> ONE global BERT batcher ->
UNBOUNDED llm_q -> llm workers that run LLM HTTP + POST + disk writes
inside the concurrency slot) with five bounded stage queues:

    producer -> prep_queue -> PREP pool (paper-level)
            -> bert_queue  -> BertGlobalBatcher (single-flight, reused Phase 1)
            -> llm_queue  -> llm dispatchers (llm_concurrency, HTTP ONLY —
                              the inference slot covers exactly run_qwen_http_stage)
            -> post_queue  -> POST pool (post_workers: glue/W2/W3/tail/merge/
                              build finalization — no disk writes)
            -> write_queue -> single writer (atomic commit + history + done)

Hard constraints (see docs/V07_PHASE2_PLAN / handoff TODO-V07-03):

- Every queue is bounded; a full downstream queue blocks its upstream
  producer (backpressure), never drops and never grows without bound.
- All terminal paths — success, PREP error, BERT batch error, BERT missing
  paper_id, LLM HTTP error, LLM parse error, POST error — go through the
  thread-safe ``_enqueue_commit`` (commit_once) gate: exactly one commit per
  paper; duplicates are counted, not written; an error can never overwrite a
  committed success.
- The writer is the only thread that touches prediction/monitor/partials/
  history files.
- Drain protocol per stage: stop upstream -> queue.join() (task_done in
  finally) -> sentinels -> worker join. The BERT batcher keeps its Phase 1
  END_OF_INPUT protocol (queue-empty != producer-done).

Frozen semantics: prompts, schema, normalize, merge, evidence, prediction
structure, checkpoint/resume (prediction_ok), error strings, BERT global
batch budgets and paper_id mapping are all reused unchanged from the
chunked/global_batch paths (parity by shared implementation path).
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from pathlib import Path
from typing import Any, Callable

from pipeline.production.batch_bert_pipeline_wf4 import (
    _SENTINEL,
    BatchBertPipelineSchedulerWf4,
    BertGlobalBatcher,
)
from pipeline.production.batch_llm_common import (
    PaperBatchState,
    PaperJob,
    build_errored_finalization,
    finalize_errored,
)
from pipeline.production.batch_llm_common_wf4 import (
    run_post_stage,
    run_qwen_http_stage,
)
from pipeline.production.monitor import utc_now
from pipeline.production.post_llm import (
    PaperFinalization,
    commit_paper_finalization,
)
from pipeline.production.test_hooks import barrier as _phase3_barrier

logger = logging.getLogger(__name__)


class _StagedQueue(queue.Queue):
    """Bounded queue that stamps enqueue perf into the job's timings.

    Items are paper_id strings (sentinels pass through untouched). The stamp
    is taken AFTER ``put`` returns (i.e. after any backpressure block), so
    ``<stage>_queue_wait`` measured at dequeue is the true in-queue wait.
    """

    def __init__(self, maxsize: int, jobs: dict[str, Any], stamp_key: str) -> None:
        super().__init__(maxsize=maxsize)
        self._jobs = jobs
        self._stamp_key = stamp_key

    def put(self, item, block=True, timeout=None):  # noqa: ANN001 — queue API
        super().put(item, block=block, timeout=timeout)
        if isinstance(item, str):
            job = self._jobs.get(item)
            if job is not None:
                job.timings[self._stamp_key] = time.perf_counter()


def _record_queue_wait(job, enqueued_key: str, wait_key: str) -> None:  # noqa: ANN001
    enq = job.timings.get(enqueued_key)
    if enq is not None:
        job.timings[wait_key] = round(max(0.0, time.perf_counter() - enq), 4)


def _pct(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, max(0, int(round((pct / 100.0) * (len(sorted_values) - 1)))))
    return sorted_values[idx]


def _agg(values: list[float]) -> dict[str, float]:
    vs = sorted(v for v in values if v is not None)
    return {
        "count": len(vs),
        "p50": round(_pct(vs, 50), 4),
        "p95": round(_pct(vs, 95), 4),
        "max": round(vs[-1], 4) if vs else 0.0,
    }


class StagedPipelineWf4(BatchBertPipelineSchedulerWf4):
    """Stage-decoupled scheduler (v0.7 Phase 2). Only window-internal
    PREP->BERT->LLM->POST->write is decoupled; manifest/window/MD-prefetch
    semantics are unchanged (run_bulk still drives one scheduler.run() per
    job_batch window).
    """

    def __init__(
        self,
        *args,
        prep_queue_maxsize: int = 128,
        bert_queue_maxsize: int | None = None,  # None -> Phase 1 default (2*max_papers)
        llm_queue_maxsize: int = 512,
        post_queue_maxsize: int = 256,
        write_queue_maxsize: int = 128,
        prep_workers: int = 4,
        post_workers: int = 8,
        rolling: bool = False,
        rolling_target: int | None = None,
        on_paper_terminal: Callable[[str, Any], None] | None = None,
        rolling_heartbeat_cb: Callable[[dict], None] | None = None,
        **kwargs,
    ) -> None:
        kwargs.setdefault("scheduler_mode", "staged")
        # rolling (TODO-V07-10): jobs are created incrementally in admit_paper
        # instead of up front; paper_ids stays admitted-pipeline-only so the
        # defensive pass never touches skipped/MD-failed papers.
        kwargs.setdefault("materialize_jobs", not rolling)
        super().__init__(*args, **kwargs)
        if self.bert_pipeline_mode != "global_batch":
            raise ValueError(
                "scheduler_mode='staged' requires bert_pipeline_mode='global_batch' "
                f"(got {self.bert_pipeline_mode!r}) — staged reuses the Phase 1 "
                "global single-flight BERT batcher."
            )
        self.prep_queue_maxsize = int(prep_queue_maxsize)
        self.bert_queue_maxsize = int(bert_queue_maxsize) if bert_queue_maxsize else None
        self.llm_queue_maxsize = int(llm_queue_maxsize)
        self.post_queue_maxsize = int(post_queue_maxsize)
        self.write_queue_maxsize = int(write_queue_maxsize)
        self.prep_workers = int(prep_workers)
        self.post_workers = int(post_workers)
        if min(self.prep_workers, self.post_workers, self.llm_concurrency) < 1:
            raise ValueError("staged worker/queue counts must be >= 1")

        # commit_once bookkeeping (single source of truth for terminal states)
        self._commit_lock = threading.Lock()
        self._commit_registry: dict[str, str] = {}  # pid -> queued|success|error|writer_error|defensive
        self.duplicate_commit_attempts: list[dict[str, Any]] = []
        self.writer_errors: list[dict[str, Any]] = []
        self.commit_counts = {"success": 0, "error": 0, "writer_error": 0, "defensive": 0}

        # observability
        self._active_lock = threading.Lock()
        self._stage_active = {"prep": 0, "llm_http": 0, "post": 0, "write": 0}
        self._stage_active_peak = dict(self._stage_active)
        self.queue_depth_max = {"prep": 0, "bert": 0, "llm": 0, "post": 0, "write": 0}

        # rolling admission state (TODO-V07-10). Window mode never sets the
        # terminal/heartbeat callbacks and skips heavy-field stripping, so its
        # behavior is byte-identical to pre-rolling code.
        self._rolling = bool(rolling)
        self.rolling_target = int(rolling_target) if rolling_target else None
        self._admit_lock = threading.Lock()
        self._rolling_terminal_seen: set[str] = set()
        self._rolling_duplicate_terminals = 0
        self._on_paper_terminal_cb = on_paper_terminal
        self._rolling_heartbeat_cb = rolling_heartbeat_cb
        self._rolling_t0: float | None = None

    # ------------------------------------------------------------- terminals

    def _fail_paper(self, job, *, source: str) -> None:  # noqa: ANN001
        """Staged failure terminal: error finalization -> write_queue (commit_once).

        Overrides the base inline-finalize behavior so that in staged mode NO
        thread other than the writer ever writes a prediction. The error
        string itself is set by the caller and is byte-identical to the
        legacy paths.
        """
        self._set_state(job, PaperBatchState.ERROR)
        fin = build_errored_finalization(
            job, spec=self.spec, run_id=self.run_id, dry_run=self.dry_run
        )
        self._enqueue_commit(job.paper_id, fin, source=source)

    def _enqueue_commit(self, pid: str, fin: PaperFinalization, *, source: str) -> bool:
        """commit_once gate: enqueue exactly one commit per paper.

        First call marks the paper ``queued`` and puts it on the write queue.
        Any later call (any thread, any path) is a no-op recorded in
        ``duplicate_commit_attempts`` — it never writes, never re-fires the
        done callback, and can never overwrite a committed result.
        """
        with self._commit_lock:
            if pid in self._commit_registry:
                self.duplicate_commit_attempts.append(
                    {
                        "paper_id": pid,
                        "source": source,
                        "existing_status": self._commit_registry[pid],
                    }
                )
                return False
            self._commit_registry[pid] = "queued"
        self.sq_write.put((pid, fin))
        job = self.jobs.get(pid)
        if job is not None:
            job.timings["_write_enqueued_perf"] = time.perf_counter()
        return True

    # ------------------------------------------------------------ activeness

    def _inc_active(self, stage: str) -> None:
        with self._active_lock:
            self._stage_active[stage] += 1
            if self._stage_active[stage] > self._stage_active_peak[stage]:
                self._stage_active_peak[stage] = self._stage_active[stage]

    def _dec_active(self, stage: str) -> None:
        with self._active_lock:
            self._stage_active[stage] -= 1

    # --------------------------------------------------------------- workers

    def _staged_prep_worker(self, batcher: BertGlobalBatcher) -> None:
        while True:
            pid = self.prep_q.get()
            try:
                if pid is _SENTINEL:
                    return
                job = self.jobs[pid]
                _record_queue_wait(job, "_prep_enqueued_perf", "prep_queue_wait")
                self._inc_active("prep")
                _phase3_barrier("prep")
                try:
                    self._set_state(job, PaperBatchState.PREP_RUNNING)
                    # _prep_paper routes its own failures through the staged
                    # _fail_paper override (error commit); on success it leaves
                    # the W1_RULES_RUNNING state + job.prepared set.
                    self._prep_paper(pid)
                    if job.state != PaperBatchState.ERROR:
                        self._set_state(job, PaperBatchState.BERT_QUEUED)
                        self._submit_to_batcher(batcher, pid)
                finally:
                    self._dec_active("prep")
            except Exception as exc:  # noqa: BLE001 — never kill the worker
                logger.warning(f"staged prep worker error for {pid}: {type(exc).__name__}: {exc}")
                if isinstance(pid, str):
                    job = self.jobs.get(pid)
                    if (
                        job is not None
                        and job.result is None
                        and pid not in self._commit_registry_view()
                    ):
                        job.error = f"prep_worker: {type(exc).__name__}: {exc}"
                        self._fail_paper(job, source="prep_worker")
            finally:
                self.prep_q.task_done()

    def _commit_registry_view(self) -> dict[str, str]:
        with self._commit_lock:
            return dict(self._commit_registry)

    # ---------------------------------------------------- rolling terminal hook

    def _on_paper_terminal(self, pid: str, result: Any) -> None:
        """Durable-terminal hook: releases the admission credit exactly once.

        No-op unless a rolling terminal callback is set — window mode never
        sets one, so commit success / writer-error diagnostics / defensive
        finalization keep their exact pre-rolling _fire_done behavior.
        """
        cb = self._on_paper_terminal_cb
        if cb is None:
            return
        with self._admit_lock:
            if pid in self._rolling_terminal_seen:
                self._rolling_duplicate_terminals += 1
                return
            self._rolling_terminal_seen.add(pid)
        try:
            cb(pid, result)
        except Exception as exc:  # noqa: BLE001 — credit release must never break the run
            logger.warning(
                f"rolling terminal callback failed for {pid}: {type(exc).__name__}: {exc}"
            )

    def _strip_after_qwen(self, job: PaperJob) -> None:
        """Rolling-only: prepared/bert_result are dead once the LLM HTTP
        stage returned (the POST pool and error finalizations only read ctx)."""
        if not self._rolling:
            return
        job.prepared = None
        job.bert_result = None

    def _strip_after_commit(self, job: PaperJob) -> None:
        """Rolling-only: after the durable commit nothing reads the heavy
        fields — defensive only touches papers whose commit FAILED, whose
        fields were therefore never stripped."""
        if not self._rolling:
            return
        ctx = job.ctx
        if ctx is not None and hasattr(ctx, "raw_md"):
            try:
                ctx.raw_md = ""
            except Exception:  # noqa: BLE001
                pass
        job.ctx = None
        job.prepared = None
        job.bert_result = None
        job.md_path = None

    def _staged_qwen_dispatcher(self) -> None:
        """LLM inference slot: covers ONLY the HTTP stage.

        After ``run_qwen_http_stage`` returns (or fails) this thread loops
        straight back to ``llm_queue.get()`` — parse/normalize/evidence/
        merge/disk all happen downstream in the POST pool / writer.
        """
        llm_client = self._make_qwen_client()
        while True:
            pid = self.sq_qwen.get()
            try:
                if pid is _SENTINEL:
                    return
                job = self.jobs[pid]
                _record_queue_wait(job, "_qwen_enqueued_perf", "llm_queue_wait")
                self._inc_active("llm_http")
                try:
                    self._set_state(job, PaperBatchState.LLM_RUNNING)
                    if self.skip_bert_filter:
                        bert_mode = job.timings.get("bert_mode", "batch")
                    else:
                        bert_mode = "batch" if not self.dry_run else "serial"
                    try:
                        _phase3_barrier("llm")
                        err = run_qwen_http_stage(
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
                        job.timings["llm_http_elapsed"] = job.timings.get("llm_elapsed_sec")
                    except Exception as exc:  # noqa: BLE001 — same string as legacy _qwen_worker
                        job.error = f"llm/post: {type(exc).__name__}: {exc}"
                        self._fail_paper(job, source="llm_http")
                        self._strip_after_qwen(job)
                        continue
                    if err is not None:
                        # Skip-on-err: parse fail / empty LLM -> no POST (same
                        # error string + skip semantics as the legacy path).
                        job.error = err
                        self._fail_paper(job, source="llm_parse")
                        self._strip_after_qwen(job)
                        continue
                    # Inference slot is released here (loop back to get());
                    # the POST stage is enqueued and runs in another pool.
                    self._set_state(job, PaperBatchState.POST_QUEUED)
                    self.sq_post.put(pid)
                    self._strip_after_qwen(job)
                finally:
                    self._dec_active("llm_http")
            except Exception as exc:  # noqa: BLE001 — never kill the worker
                logger.warning(f"staged llm dispatcher error: {type(exc).__name__}: {exc}")
            finally:
                self.sq_qwen.task_done()

    def _staged_post_worker(self) -> None:
        while True:
            pid = self.sq_post.get()
            try:
                if pid is _SENTINEL:
                    return
                job = self.jobs[pid]
                _record_queue_wait(job, "_post_enqueued_perf", "post_queue_wait")
                self._inc_active("post")
                try:
                    if self.skip_bert_filter:
                        bert_mode = job.timings.get("bert_mode", "batch")
                    else:
                        bert_mode = "batch" if not self.dry_run else "serial"
                    try:
                        _phase3_barrier("post")
                        fin = run_post_stage(
                            job,
                            spec=self.spec,
                            run_id=self.run_id,
                            dry_run=self.dry_run,
                            bert_mode=bert_mode,
                            lock=self._lock,
                            input_path=job.timings.get("input_path"),
                        )
                        job.timings["post_elapsed"] = job.timings.get("post_llm_elapsed_sec")
                    except Exception as exc:  # noqa: BLE001 — same string as legacy path
                        job.error = f"llm/post: {type(exc).__name__}: {exc}"
                        self._fail_paper(job, source="post")
                        continue
                    self._set_state(job, PaperBatchState.WRITE_QUEUED)
                    self._enqueue_commit(pid, fin, source="post_success")
                finally:
                    self._dec_active("post")
            except Exception as exc:  # noqa: BLE001 — never kill the worker
                logger.warning(f"staged post worker error: {type(exc).__name__}: {exc}")
            finally:
                self.sq_post.task_done()

    def _staged_writer(self) -> None:
        """Single writer: the only thread that commits finalizations to disk."""
        while True:
            item = self.sq_write.get()
            try:
                if item is _SENTINEL:
                    return
                pid, fin = item
                job = self.jobs.get(pid)
                self._inc_active("write")
                _phase3_barrier("write")
                try:
                    enq = job.timings.get("_write_enqueued_perf") if job is not None else None
                    if job is not None and enq is not None:
                        # Record at dequeue: pure in-queue wait, NOT including
                        # the commit's disk IO below (all other stages record
                        # their queue wait at dequeue too).
                        job.timings["write_queue_wait"] = round(
                            max(0.0, time.perf_counter() - enq), 4
                        )
                        # The pipeline_stages snapshot was taken in the POST
                        # worker before enqueue; backfill so the per-paper
                        # monitor carries the field (collect_phase_metrics
                        # already lists it). We are the single writer thread
                        # and the monitor is serialized inside commit below.
                        ps = fin.monitor.get("pipeline_stages")
                        if isinstance(ps, dict):
                            ps["write_queue_wait"] = job.timings["write_queue_wait"]
                    t_commit = time.perf_counter()
                    result = commit_paper_finalization(fin)
                    if job is not None:
                        job.timings["write_elapsed_sec"] = round(
                            max(0.0, time.perf_counter() - t_commit), 4
                        )
                        job.result = result
                    with self._commit_lock:
                        status = "error" if fin.error else "success"
                        self._commit_registry[pid] = status
                        self.commit_counts[status] += 1
                    if job is not None:
                        self._set_state(
                            job,
                            PaperBatchState.COMMITTED_ERROR
                            if fin.error
                            else PaperBatchState.COMMITTED_SUCCESS,
                        )
                        self._fire_done(job)
                    # durable terminal (success AND error commits): release the
                    # rolling admission credit; no-op in window mode.
                    self._on_paper_terminal(pid, result)
                    if job is not None:
                        self._strip_after_commit(job)
                except Exception as exc:  # noqa: BLE001 — writer must survive
                    with self._commit_lock:
                        self._commit_registry[pid] = "writer_error"
                        self.commit_counts["writer_error"] += 1
                        self.writer_errors.append(
                            {"paper_id": pid, "error": f"{type(exc).__name__}: {exc}"}
                        )
                    logger.warning(f"staged writer commit failed for {pid}: {type(exc).__name__}: {exc}")
                finally:
                    self._dec_active("write")
            finally:
                self.sq_write.task_done()

    def _rolling_snapshot(self) -> dict[str, Any]:
        """Light heartbeat payload (no heavy objects; ints copied only)."""
        return {
            "admitted": len(self.paper_ids),
            "rolling_target": self.rolling_target,
            "queue_depth_max": dict(self.queue_depth_max),
            "stage_active_peak": dict(self._stage_active_peak),
        }

    def _staged_sampler(
        self,
        stop_event: threading.Event,
        queues: dict[str, queue.Queue],
        heartbeat: Callable[[dict], None] | None = None,
    ) -> None:
        last_hb = 0.0
        while not stop_event.wait(0.1):
            for name, q in queues.items():
                depth = q.qsize()
                if depth > self.queue_depth_max[name]:
                    self.queue_depth_max[name] = depth
            if heartbeat is not None:
                now = time.perf_counter()
                if now - last_hb >= 1.0:
                    last_hb = now
                    try:
                        heartbeat(self._rolling_snapshot())
                    except Exception:  # noqa: BLE001 — heartbeat must never break sampling
                        logger.warning("rolling heartbeat callback failed", exc_info=True)

    # ------------------------------------------------------------------- run

    def run(self) -> list:
        return self._run_staged()

    # ------------------------------------------------- staged runtime lifecycle
    #
    # _run_staged (window) = create -> start -> produce all -> drain ->
    # finalize. Rolling (TODO-V07-10) reuses the same pieces: start_rolling()
    # keeps the runtime resident for the whole job_batch, admit_paper() feeds
    # papers one credit at a time, finish_rolling_input() runs the UNCHANGED
    # sentinel/drain protocol once the admission cursor is exhausted.

    def _create_staged_runtime(self) -> None:
        # --- queues (all bounded) -------------------------------------------
        self.prep_q = _StagedQueue(self.prep_queue_maxsize, self.jobs, "_prep_enqueued_perf")
        self.sq_qwen = _StagedQueue(self.llm_queue_maxsize, self.jobs, "_qwen_enqueued_perf")
        self.sq_post = _StagedQueue(self.post_queue_maxsize, self.jobs, "_post_enqueued_perf")
        self.sq_write = queue.Queue(maxsize=self.write_queue_maxsize)
        # Base-class helpers (_global_dispatch, the dry-run branch of
        # _submit_to_batcher) put to self.llm_q — alias it to the bounded
        # staged queue so every BERT-stage dispatch is backpressured.
        self.llm_q = self.sq_qwen

        # --- BERT stage: Phase 1 single-flight global batcher, reused -------
        self._batcher = BertGlobalBatcher(
            max_papers=self.bert_batch_max_papers,
            max_sentences=self.bert_batch_max_sentences,
            max_chars=self.bert_batch_max_chars,
            max_wait_ms=self.bert_batch_max_wait_ms,
            batch_fn=self._global_batch_fn,
            dispatch_fn=self._global_dispatch,
            error_fn=self._global_batch_error,
            batch_index_start=self._existing_global_batch_count(),
            inbound_maxsize=self.bert_queue_maxsize,
            jobs=self.jobs,
            endpoint_concurrency=self.bert_endpoint_concurrency,
        )
        self._batcher_thread = threading.Thread(
            target=self._batcher.run, name="staged-bert-batcher", daemon=True
        )

        # --- workers ---------------------------------------------------------
        self._prep_threads = [
            threading.Thread(
                target=self._staged_prep_worker,
                args=(self._batcher,),
                name=f"staged-prep-{i}",
                daemon=True,
            )
            for i in range(self.prep_workers)
        ]
        self._qwen_threads = [
            threading.Thread(
                target=self._staged_qwen_dispatcher, name=f"staged-llm-{i}", daemon=True
            )
            for i in range(self.llm_concurrency)
        ]
        self._post_threads = [
            threading.Thread(
                target=self._staged_post_worker, name=f"staged-post-{i}", daemon=True
            )
            for i in range(self.post_workers)
        ]
        self._writer_thread = threading.Thread(
            target=self._staged_writer, name="staged-writer", daemon=True
        )
        self._sampler_stop = threading.Event()
        self._sampler_thread = threading.Thread(
            target=self._staged_sampler,
            args=(
                self._sampler_stop,
                {
                    "prep": self.prep_q,
                    "bert": self._batcher.inbound,
                    "llm": self.sq_qwen,
                    "post": self.sq_post,
                    "write": self.sq_write,
                },
                self._rolling_heartbeat_cb,
            ),
            name="staged-sampler",
            daemon=True,
        )

    def _start_staged_runtime(self) -> None:
        self._batcher_thread.start()
        for t in self._prep_threads:
            t.start()
        for t in self._qwen_threads:
            t.start()
        for t in self._post_threads:
            t.start()
        self._writer_thread.start()
        self._sampler_thread.start()

    def _drain_staged_runtime(self) -> None:
        # --- drain protocol (per stage: stop upstream -> join() -> sentinel) -
        for _ in range(self.prep_workers):
            self.prep_q.put(_SENTINEL)
        for t in self._prep_threads:
            t.join()
        self.prep_q.join()  # drain evidence: no unfinished tasks remain

        self._batcher.end_of_input()  # END_OF_INPUT: flush remainder, finish in-flight HTTP
        self._batcher_thread.join()  # == BERT_DONE

        self.sq_qwen.join()
        for _ in range(self.llm_concurrency):
            self.sq_qwen.put(_SENTINEL)
        for t in self._qwen_threads:
            t.join()

        self.sq_post.join()
        for _ in range(self.post_workers):
            self.sq_post.put(_SENTINEL)
        for t in self._post_threads:
            t.join()

        self.sq_write.join()
        self.sq_write.put(_SENTINEL)
        self._writer_thread.join()

        self._sampler_stop.set()
        self._sampler_thread.join()

    def _finalize_staged_batch(self, run_started: float) -> list:
        wall_sec = round(time.perf_counter() - run_started, 4)

        # --- BERT batch monitor: same shape/append semantics as global_batch -
        self.batch_monitor = {
            "pipeline_mode": "global_batch",
            "scheduler_mode": "staged",
            "batches": self._batcher.batches,
            "batch_count": len(self._batcher.batches),
            "bert_batch_max_papers": self.bert_batch_max_papers,
            "bert_batch_max_sentences": self.bert_batch_max_sentences,
            "bert_batch_max_chars": self.bert_batch_max_chars,
            "bert_batch_max_wait_ms": self.bert_batch_max_wait_ms,
            "bert_endpoint_concurrency": self.bert_endpoint_concurrency,
            "sum_batch_bert_sec": round(
                sum(b.get("bert_client_sec", 0.0) for b in self._batcher.batches), 4
            ),
        }
        self._write_global_batch_monitor(self.batch_monitor)

        # --- defensive pass: ONLY papers that were never committed ----------
        # (result is None <=> no successful commit: absent, or writer_error).
        # Committed successes/errors are never touched again.
        defensive: list[dict[str, Any]] = []
        registry_before = self._commit_registry_view()
        for pid in self.paper_ids:
            job = self.jobs[pid]
            if job.result is not None:
                continue
            if job.error is None:
                job.error = "no_result_set"
            self._set_state(job, PaperBatchState.ERROR)
            finalize_errored(job, spec=self.spec, run_id=self.run_id, dry_run=self.dry_run)
            with self._commit_lock:
                self._commit_registry[pid] = "defensive"
                self.commit_counts["defensive"] += 1
            defensive.append(
                {"paper_id": pid, "prior_status": registry_before.get(pid, "absent")}
            )
            self._fire_done(job)
            # defensive finalization is this paper's durable terminal
            self._on_paper_terminal(pid, job.result)
            self._strip_after_commit(job)

        if self._rolling:
            self._write_staged_monitor_rolling(wall_sec, defensive)
        else:
            self._write_staged_monitor(wall_sec, defensive)

        return [self.jobs[pid].result for pid in self.paper_ids]

    def _run_staged(self) -> list:
        if self._rolling:
            raise RuntimeError(
                "rolling scheduler: use start_rolling()/admit_paper()/finish_rolling_input(), not run()"
            )
        run_started = time.perf_counter()
        self._create_staged_runtime()
        self._start_staged_runtime()

        # --- producer: window paper_ids -> prep_queue (blocks when full) ----
        for pid in self.paper_ids:
            job = self.jobs[pid]
            self._set_state(job, PaperBatchState.PREP_QUEUED)
            self.prep_q.put(pid)

        self._drain_staged_runtime()
        return self._finalize_staged_batch(run_started)

    # ------------------------------------------------------------ rolling API

    def start_rolling(self) -> None:
        """Start the resident runtime (queues/batcher/workers/sampler) without
        producing anything — the controller feeds papers via admit_paper()."""
        if not self._rolling:
            raise RuntimeError("start_rolling() requires rolling=True")
        self._rolling_t0 = time.perf_counter()
        self._create_staged_runtime()
        self._start_staged_runtime()

    def admit_paper(self, pid: str, md_path: Path) -> None:
        """Incrementally register + enqueue ONE admitted pipeline paper.

        Registration (light PaperJob, jobs dict, paper_ids, state) happens
        under the admission lock; the potentially-blocking bounded prep_q.put
        runs OUTSIDE the lock so queue backpressure never holds off terminal
        callbacks. paper_ids stays admitted-pipeline-only (skipped/MD-failed
        papers never appear here — the defensive pass cannot touch them).
        """
        if not self._rolling:
            raise RuntimeError("admit_paper() requires rolling=True")
        if not hasattr(self, "prep_q"):
            raise RuntimeError("admit_paper() requires start_rolling() first")
        with self._admit_lock:
            if pid in self.jobs:
                raise ValueError(f"rolling admission: duplicate paper_id {pid!r}")
            job = PaperJob(
                paper_id=pid,
                md_path=md_path,
                run_id=self.run_id,
                spec=self.spec,
                dry_run=self.dry_run,
            )
            self.jobs[pid] = job
            self.paper_ids.append(pid)
        self._set_state(job, PaperBatchState.PREP_QUEUED)
        try:
            self.prep_q.put(pid)  # bounded — may block; NO lock held
        except Exception:  # noqa: BLE001 — roll the registration back
            with self._admit_lock:
                self.jobs.pop(pid, None)
                if pid in self.paper_ids:
                    self.paper_ids.remove(pid)
            raise

    def finish_rolling_input(self) -> list:
        """Cursor exhausted (or STOP): run the UNCHANGED drain protocol, then
        the defensive pass + monitors. END_OF_INPUT fires only here, so the
        BERT_DONE/batch_index contracts hold exactly as in window mode."""
        if not self._rolling:
            raise RuntimeError("finish_rolling_input() requires rolling=True")
        if self._rolling_t0 is None:
            raise RuntimeError("finish_rolling_input() requires start_rolling() first")
        started = self._rolling_t0 if self._rolling_t0 is not None else time.perf_counter()
        self._drain_staged_runtime()
        return self._finalize_staged_batch(started)

    # --------------------------------------------------------------- monitor

    def _write_staged_monitor(self, wall_sec: float, defensive: list[dict[str, Any]]) -> None:
        from pipeline.production.config import RUNS_DIR

        def collect(key: str) -> list[float]:
            return [
                j.timings[key]
                for j in self.jobs.values()
                if isinstance(j.timings.get(key), (int, float))
            ]

        timing_aggs = {
            "prep_queue_wait": _agg(collect("prep_queue_wait")),
            "bert_queue_wait": _agg(collect("bert_queue_wait")),
            "llm_queue_wait": _agg(collect("llm_queue_wait")),
            "llm_http_elapsed": _agg(collect("llm_http_elapsed")),
            "post_queue_wait": _agg(collect("post_queue_wait")),
            "post_elapsed": _agg(collect("post_elapsed")),
            "write_queue_wait": _agg(collect("write_queue_wait")),
            "write_elapsed_sec": _agg(collect("write_elapsed_sec")),
            "paper_wall_sec": _agg(collect("paper_wall_sec")),
        }

        registry = self._commit_registry_view()
        payload = {
            "run_id": self.run_id,
            "workflow_id": self.spec.workflow_id,
            "scheduler_mode": "staged",
            "pipeline_mode": "global_batch",
            "paper_count": len(self.paper_ids),
            "wall_sec": wall_sec,
            "params": {
                "prep_queue_maxsize": self.prep_queue_maxsize,
                "bert_queue_maxsize": self.bert_queue_maxsize or 2 * self.bert_batch_max_papers,
                "llm_queue_maxsize": self.llm_queue_maxsize,
                "post_queue_maxsize": self.post_queue_maxsize,
                "write_queue_maxsize": self.write_queue_maxsize,
                "prep_workers": self.prep_workers,
                "llm_concurrency": self.llm_concurrency,
                "post_workers": self.post_workers,
                "writer": 1,
            },
            "queue_depth_max": dict(self.queue_depth_max),
            "stage_active_peak": dict(self._stage_active_peak),
            "commit_counts": dict(self.commit_counts),
            "terminal_states": {
                status: sum(1 for s in registry.values() if s == status)
                for status in ("success", "error", "writer_error", "defensive")
            },
            "duplicate_commit_attempts": list(self.duplicate_commit_attempts),
            "writer_errors": list(self.writer_errors),
            "defensive_finalizes": defensive,
            "timings": timing_aggs,
            "written_at": utc_now(),
        }

        run_dir = RUNS_DIR / self.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / "staged_pipeline_monitor.json"
        # append-per-window (mirrors _write_global_batch_monitor semantics)
        windows = [payload]
        if path.is_file():
            try:
                prev = json.loads(path.read_text(encoding="utf-8"))
                windows = list(prev.get("windows") or [prev]) + [payload]
            except Exception:  # noqa: BLE001 — corrupt monitor -> start fresh
                windows = [payload]
        doc = {"run_id": self.run_id, "window_count": len(windows), "windows": windows}
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, path)

    def _write_staged_monitor_rolling(self, wall_sec: float, defensive: list[dict[str, Any]]) -> None:
        """Rolling monitor: ONE flat payload per job_batch — no windows[] append,
        no pseudo-window. Consumers read either shape via
        ``doc.get("windows") or [doc]`` (phase3_kill_restart._staged_monitor_totals)."""
        from pipeline.production.config import RUNS_DIR

        def collect(key: str) -> list[float]:
            return [
                j.timings[key]
                for j in self.jobs.values()
                if isinstance(j.timings.get(key), (int, float))
            ]

        timing_aggs = {
            "prep_queue_wait": _agg(collect("prep_queue_wait")),
            "bert_queue_wait": _agg(collect("bert_queue_wait")),
            "llm_queue_wait": _agg(collect("llm_queue_wait")),
            "llm_http_elapsed": _agg(collect("llm_http_elapsed")),
            "post_queue_wait": _agg(collect("post_queue_wait")),
            "post_elapsed": _agg(collect("post_elapsed")),
            "write_queue_wait": _agg(collect("write_queue_wait")),
            "write_elapsed_sec": _agg(collect("write_elapsed_sec")),
            "paper_wall_sec": _agg(collect("paper_wall_sec")),
        }

        registry = self._commit_registry_view()
        payload = {
            "run_id": self.run_id,
            "workflow_id": self.spec.workflow_id,
            "scheduler_mode": "staged",
            "pipeline_mode": "global_batch",
            "admission_mode": "rolling",
            "admission": {
                "rolling_target": self.rolling_target,
                "admitted": len(self.paper_ids),
                "terminal_registry": len(registry),
                "duplicate_terminal_callbacks": self._rolling_duplicate_terminals,
            },
            "paper_count": len(self.paper_ids),
            "wall_sec": wall_sec,
            "papers_per_hour": (
                round(len(self.paper_ids) / wall_sec * 3600.0, 2) if wall_sec > 0 else None
            ),
            "params": {
                "prep_queue_maxsize": self.prep_queue_maxsize,
                "bert_queue_maxsize": self.bert_queue_maxsize or 2 * self.bert_batch_max_papers,
                "llm_queue_maxsize": self.llm_queue_maxsize,
                "post_queue_maxsize": self.post_queue_maxsize,
                "write_queue_maxsize": self.write_queue_maxsize,
                "prep_workers": self.prep_workers,
                "llm_concurrency": self.llm_concurrency,
                "post_workers": self.post_workers,
                "writer": 1,
                "rolling_target": self.rolling_target,
            },
            "queue_depth_max": dict(self.queue_depth_max),
            "stage_active_peak": dict(self._stage_active_peak),
            "commit_counts": dict(self.commit_counts),
            "terminal_states": {
                status: sum(1 for s in registry.values() if s == status)
                for status in ("success", "error", "writer_error", "defensive")
            },
            "duplicate_commit_attempts": list(self.duplicate_commit_attempts),
            "writer_errors": list(self.writer_errors),
            "defensive_finalizes": defensive,
            "timings": timing_aggs,
            "written_at": utc_now(),
        }

        run_dir = RUNS_DIR / self.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / "staged_pipeline_monitor.json"
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, path)
