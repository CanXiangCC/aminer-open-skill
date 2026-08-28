"""v0.7 Phase 1 tests: BertGlobalBatcher unit / lifecycle / parity / conservation.

No HTTP mocking precedent exists in this repo; the parity test monkeypatches
``pipeline.production.adapters.bert_batch_client.filter_papers_batch`` (the
adapter imports it lazily inside the function body, so the module attribute is
resolved at call time). Everything else uses injected fakes (batch_fn /
dispatch_fn / error_fn), matching the repo's monkeypatch + fake-object style.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from pipeline.production.batch_bert_pipeline_wf4 import BertGlobalBatcher


@dataclass
class FakePrepared:
    english_sentences: list[str] = field(default_factory=list)


def make_batcher(
    *,
    max_papers=16,
    max_sentences=1500,
    max_chars=300_000,
    max_wait_ms=20,
    batch_fn=None,
    dispatch_fn=None,
    error_fn=None,
    endpoint_concurrency=1,
):
    calls: list[dict[str, Any]] = {"batches": [], "dispatched": [], "errors": []}

    def default_batch_fn(prepared_map):
        calls["batches"].append(list(prepared_map.keys()))
        return {pid: f"result-{pid}" for pid in prepared_map}

    def default_dispatch_fn(results, pids, stat):
        calls["dispatched"].append((list(pids), dict(results), dict(stat)))

    def default_error_fn(pids, err):
        calls["errors"].append((list(pids), err))

    b = BertGlobalBatcher(
        max_papers=max_papers,
        max_sentences=max_sentences,
        max_chars=max_chars,
        max_wait_ms=max_wait_ms,
        batch_fn=batch_fn or default_batch_fn,
        dispatch_fn=dispatch_fn or default_dispatch_fn,
        error_fn=error_fn or default_error_fn,
        endpoint_concurrency=endpoint_concurrency,
    )
    return b, calls


def run_sync(batcher: BertGlobalBatcher, papers: list[tuple[str, FakePrepared]]) -> None:
    # Real-world shape: the batcher thread consumes WHILE the producer submits
    # (the inbound queue is bounded — a sync submit-then-run would deadlock on
    # queue capacity, which is exactly the backpressure we want in production).
    t = threading.Thread(target=batcher.run, daemon=True)
    t.start()
    for pid, prepared in papers:
        batcher.submit(pid, prepared)
    batcher.end_of_input()
    t.join(timeout=10.0)
    assert not t.is_alive(), "batcher thread did not finish (BERT_DONE never emitted)"


# ---------------------------------------------------------------- unit: flush


def test_flush_on_max_papers():
    b, calls = make_batcher(max_papers=3)
    papers = [(f"p{i}", FakePrepared([f"s{i}."])) for i in range(6)]
    run_sync(b, papers)
    sizes = [len(g) for g in calls["batches"]]
    assert sizes == [3, 3]  # last 0 papers -> no third batch
    assert all(s["flush_reason"] == "max_papers" for _, _, s in calls["dispatched"][:2])


def test_flush_on_max_sentences():
    b, calls = make_batcher(max_papers=16, max_sentences=10)
    papers = [
        ("p0", FakePrepared(["s."] * 6)),
        ("p1", FakePrepared(["s."] * 6)),  # 6+6 > 10 -> flush [p0] first
        ("p2", FakePrepared(["s."] * 6)),  # 6+6 > 10 -> flush [p1] first
    ]
    run_sync(b, papers)
    assert calls["batches"] == [["p0"], ["p1"], ["p2"]]
    assert calls["dispatched"][0][2]["flush_reason"] == "max_sentences"
    assert calls["dispatched"][1][2]["flush_reason"] == "max_sentences"
    assert calls["dispatched"][2][2]["flush_reason"] == "end_of_input"


def test_flush_on_max_chars():
    b, calls = make_batcher(max_papers=16, max_chars=20)
    papers = [
        ("p0", FakePrepared(["x" * 12])),
        ("p1", FakePrepared(["x" * 12])),  # 12+12 > 20 -> flush [p0] first
        ("p2", FakePrepared(["x" * 12])),  # 12+12 > 20 -> flush [p1] first
    ]
    run_sync(b, papers)
    assert calls["batches"] == [["p0"], ["p1"], ["p2"]]
    assert calls["dispatched"][0][2]["flush_reason"] == "max_chars"
    assert calls["dispatched"][1][2]["flush_reason"] == "max_chars"
    assert calls["dispatched"][2][2]["flush_reason"] == "end_of_input"


def test_flush_on_max_wait_ms():
    # Threaded run: two papers, then a pause in the producer -> the batcher
    # must flush on max_wait_ms even though end_of_input has NOT arrived
    # ("queue empty" != "producer done").
    b, calls = make_batcher(max_wait_ms=80)
    t = threading.Thread(target=b.run, daemon=True)
    t.start()
    b.submit("p0", FakePrepared(["s."]))
    b.submit("p1", FakePrepared(["s."]))
    deadline = time.monotonic() + 2.0
    while not calls["dispatched"] and time.monotonic() < deadline:
        time.sleep(0.01)
    assert calls["dispatched"], "batcher did not flush on max_wait_ms"
    assert calls["dispatched"][0][2]["flush_reason"] == "max_wait_ms"
    b.end_of_input()
    t.join(timeout=2.0)
    assert not t.is_alive()


def test_empty_input_no_batch():
    b, calls = make_batcher()
    b.end_of_input()
    b.run()
    assert calls["batches"] == []
    assert calls["dispatched"] == []
    assert calls["errors"] == []


def test_oversized_single_paper_sent_alone():
    # A single paper larger than the sentence budget is never split/starved:
    # it flushes alone, and the NEXT paper starts a fresh group.
    b, calls = make_batcher(max_sentences=5)
    papers = [
        ("huge", FakePrepared(["s."] * 40)),
        ("normal", FakePrepared(["s."] * 3)),
    ]
    run_sync(b, papers)
    assert calls["batches"] == [["huge"], ["normal"]]
    assert calls["dispatched"][0][2]["sentence_count"] == 40
    assert calls["dispatched"][1][2]["flush_reason"] == "end_of_input"


def test_duplicate_paper_id_explicit_error():
    b, calls = make_batcher()
    papers = [("p0", FakePrepared(["s."])), ("p0", FakePrepared(["s."]))]
    run_sync(b, papers)
    assert calls["batches"] == [["p0"]]  # duplicate never batched
    assert len(calls["errors"]) == 1
    assert calls["errors"][0][0] == ["p0"]
    assert "duplicate paper_id" in calls["errors"][0][1]


# ------------------------------------------------- unit: lifecycle & failures


def test_producer_done_partial_batch_flushed():
    # END_OF_INPUT with an unfilled group -> remainder MUST flush.
    b, calls = make_batcher(max_papers=100)
    papers = [(f"p{i}", FakePrepared(["s."])) for i in range(5)]
    run_sync(b, papers)
    assert calls["batches"] == [["p0", "p1", "p2", "p3", "p4"]]
    assert calls["dispatched"][0][2]["flush_reason"] == "end_of_input"


def test_end_of_input_waits_for_inflight_batch():
    # A slow in-flight batch_fn must complete (and dispatch) before run()
    # returns on END_OF_INPUT — shutdown never drops an in-flight request.
    started = threading.Event()
    release = threading.Event()

    def slow_batch_fn(prepared_map):
        started.set()
        release.wait(timeout=5.0)
        return {pid: f"r-{pid}" for pid in prepared_map}

    b, calls = make_batcher(batch_fn=slow_batch_fn)
    t = threading.Thread(target=b.run, daemon=True)
    t.start()
    b.submit("p0", FakePrepared(["s."]))
    assert started.wait(timeout=2.0)
    b.end_of_input()
    # run() must NOT return while the flush is still in flight
    assert t.is_alive()
    release.set()
    t.join(timeout=2.0)
    assert not t.is_alive()
    # the in-flight batch completed and dispatched before BERT_DONE
    assert len(calls["dispatched"]) == 1


def test_batch_failure_isolated_to_batch():
    # batch_fn raises for the FIRST group only: those papers go to error_fn,
    # subsequent groups are still processed (window continues).
    state = {"n": 0}

    def flaky_batch_fn(prepared_map):
        state["n"] += 1
        if state["n"] == 1:
            raise ConnectionError("cluster unreachable")
        return {pid: f"r-{pid}" for pid in prepared_map}

    b, calls = make_batcher(max_papers=2, batch_fn=flaky_batch_fn)
    papers = [(f"p{i}", FakePrepared(["s."])) for i in range(4)]
    run_sync(b, papers)
    groups = [bt["paper_ids"] for bt in b.batches]
    assert groups[0] == ["p0", "p1"]
    assert len(calls["errors"]) == 1
    errored_pids, err = calls["errors"][0]
    assert errored_pids == ["p0", "p1"]
    assert "bert_batch_failed" in err
    assert "ConnectionError" in err
    assert groups[1] == ["p2", "p3"]
    assert calls["dispatched"][0][0] == ["p2", "p3"]
    # failure recorded in the batch stat (observability)
    assert "error" in b.batches[0]


def test_missing_paper_in_response_not_silent():
    # A 200 response missing a paper_id surfaces as an absent pid in the
    # results dict handed to dispatch_fn — the SCHEDULER marks it errored.
    # Here we assert the batcher contract: dispatch gets exactly what the
    # (server) returned, missing pid included in pids but not in results.
    def dropping_batch_fn(prepared_map):
        return {pid: f"r-{pid}" for pid in prepared_map if pid != "p1"}

    b, calls = make_batcher(batch_fn=dropping_batch_fn)
    run_sync(b, [("p0", FakePrepared(["s."])), ("p1", FakePrepared(["s."]))])
    pids, results, _stat = calls["dispatched"][0]
    assert pids == ["p0", "p1"]
    assert set(results.keys()) == {"p0"}  # p1 missing -> scheduler errors it


def test_conservation_no_silent_drop():
    # Every submitted paper appears in exactly one batch; failed-batch papers
    # are reported through error_fn, never silently dropped.
    def sometimes_failing(prepared_map):
        if "p13" in prepared_map:
            raise TimeoutError("read timeout")
        return {pid: f"r-{pid}" for pid in prepared_map}

    b, calls = make_batcher(max_papers=7, batch_fn=sometimes_failing)
    papers = [(f"p{i}", FakePrepared(["s."] * (i % 5 + 1))) for i in range(30)]
    run_sync(b, papers)
    batched = [pid for bt in b.batches for pid in bt["paper_ids"]]
    errored = [pid for pids, _ in calls["errors"] for pid in pids]
    assert len(batched) == len(set(batched)) == 30  # each paper exactly once
    # p13's whole group (p13 + its batchmates) failed, nothing else
    assert errored == calls["errors"][0][0]
    assert "p13" in errored
    dispatched_ok = [pid for pids, _, _ in calls["dispatched"] for pid in pids]
    assert sorted(dispatched_ok + errored) == sorted(f"p{i}" for i in range(30))


def test_batch_stats_record_budgets():
    b, calls = make_batcher(max_papers=4)
    papers = [
        ("p0", FakePrepared(["s."] * 3)),
        ("p1", FakePrepared(["x" * 10, "y" * 20])),
    ]
    run_sync(b, papers)
    stat = calls["dispatched"][0][2]
    assert stat["paper_count"] == 2
    assert stat["sentence_count"] == 5
    assert stat["char_count"] == 3 * 2 + 30  # "s."*3 (6) + "x"*10 + "y"*20
    assert stat["max_sentence_chars"] == 20
    assert stat["flush_reason"] == "end_of_input"
    assert stat["batch_index"] == 0
    assert "bert_client_sec" in stat


# ---------------------------------------------------------------- parity


def _fake_filter_papers_batch(papers, *, threshold=0.6, batch_size=32, url=None, **kwargs):
    """Deterministic fake /filter/batch implementing the REAL server contract:
    per-paper local 0-based indices aligned to the input sentence list,
    confidences aligned to kept ONLY, papers[] possibly reordered."""
    out_papers = []
    total_sentences = total_kept = 0
    for p in papers:
        sents = p["sentences"]
        kept_idx = [i for i, s in enumerate(sents) if "keep" in s]
        kept = [sents[i] for i in kept_idx]
        confs = [0.9 - 0.01 * i for i in range(len(kept))]
        out_papers.append(
            {
                "paper_id": p["paper_id"],
                "kept": kept,
                "indices": kept_idx,
                "confidences": confs,
                "total": len(sents),
                "kept_count": len(kept),
            }
        )
        total_sentences += len(sents)
        total_kept += len(kept)
    return {
        "papers": out_papers,
        "paper_count": len(out_papers),
        "total_sentences": total_sentences,
        "total_kept": total_kept,
        "inference_time_ms": 12.3,
        "batch_size": batch_size,
        "client_elapsed_sec": 0.5,
    }


def _make_fake_prepared(n_papers=23, seed=7):
    import random

    rng = random.Random(seed)
    prepared = {}
    for i in range(n_papers):
        n = rng.randint(5, 25)
        sents = []
        for j in range(n):
            word = "keep" if (i + j) % 3 == 0 else "drop"
            sents.append(f"{word} sentence {i}-{j} " + "z" * rng.randint(0, 15))
        prepared[f"paper-{i:03d}"] = FakePrepared(sents)
    return prepared


def _result_signature(res):
    return (
        list(res.llm_input),
        dict(res.sentence_selection),
        dict(res.bert_raw),
    )


def test_parity_chunked_vs_global_batch(monkeypatch):
    """Same fixtures, two groupings: fixed 10-paper chunks (chunked path's
    adapter call) vs batcher-formed cross-chunk groups in SHUFFLED arrival
    order — per-paper results must be identical (parity by shared
    implementation path, validated here explicitly)."""
    import pipeline.production.adapters.bert_batch_client as bbc
    from pipeline.production.adapters.wf4_stages import run_bert_batch_for_papers_wf4

    monkeypatch.setattr(bbc, "filter_papers_batch", _fake_filter_papers_batch)

    prepared = _make_fake_prepared(23)

    # Old path: fixed 10-paper chunks (what _run_bert_chunk asks the adapter).
    results_old, _ = run_bert_batch_for_papers_wf4(
        dict(prepared), max_sentences=60, chunk_max_papers=10, batch_size=32
    )

    # New path: batcher groups (max_papers=16; shuffle arrival order), each
    # group one-shot through the SAME adapter (what _global_batch_fn does).
    collected: dict[str, Any] = {}
    lock = threading.Lock()

    def batch_fn(group_map):
        res, _ = run_bert_batch_for_papers_wf4(
            group_map, max_sentences=60, chunk_max_papers=len(group_map), batch_size=32
        )
        return res

    def dispatch_fn(results, pids, stat):
        with lock:
            collected.update(results)

    b = BertGlobalBatcher(max_papers=16, max_wait_ms=10, batch_fn=batch_fn, dispatch_fn=dispatch_fn)
    order = list(prepared.items())
    import random

    random.Random(3).shuffle(order)  # arrival order != manifest order
    t = threading.Thread(target=b.run, daemon=True)
    t.start()
    for pid, prep in order:
        b.submit(pid, prep)
    b.end_of_input()
    t.join(timeout=5.0)
    assert not t.is_alive()

    # conservation through the adapter too
    assert set(collected.keys()) == set(prepared.keys())
    assert sum(len(g) for g in [bt["paper_ids"] for bt in b.batches]) == 23

    for pid, res_old in results_old.items():
        assert pid in collected, f"paper {pid} missing from global-batch results"
        assert _result_signature(collected[pid]) == _result_signature(res_old), (
            f"parity broken for {pid}"
        )


def test_parity_out_of_order_response_mapping(monkeypatch):
    """The server may return papers[] in a different order than the request:
    mapping is by paper_id, never by position."""
    import pipeline.production.adapters.bert_batch_client as bbc
    from pipeline.production.adapters.wf4_stages import run_bert_batch_for_papers_wf4

    def reversed_filter(papers, **kwargs):
        data = _fake_filter_papers_batch(papers, **kwargs)
        data["papers"] = list(reversed(data["papers"]))
        return data

    monkeypatch.setattr(bbc, "filter_papers_batch", reversed_filter)

    prepared = _make_fake_prepared(9, seed=11)
    results, _ = run_bert_batch_for_papers_wf4(
        dict(prepared), max_sentences=60, chunk_max_papers=9, batch_size=32
    )
    assert set(results.keys()) == set(prepared.keys())
    for pid, res in results.items():
        sents = prepared[pid].english_sentences
        kept = [s for s in sents if "keep" in s]  # <= 60 here -> no truncation
        assert res.llm_input == kept  # document order preserved, mapped by id
        assert res.sentence_selection["total_kept"] == len(kept)
        assert res.sentence_selection["truncated"] is False
        assert res.bert_raw["total"] == len(sents)
        assert res.bert_raw["kept_count"] == len(kept)


# ------------------------------------------- unit: per-paper bert_queue_wait


def test_bert_queue_wait_recorded_per_paper():
    """bert_queue_wait = submit (PREP handoff) -> that batch's HTTP start.
    With max_papers=1 the first paper flushes immediately (wait ~0) while the
    second waits in inbound/pending through the first batch's HTTP call."""
    jobs = {
        "p0": SimpleNamespace(timings={}),
        "p1": SimpleNamespace(timings={}),
    }
    calls = {"n": 0}

    def slow_first_batch_fn(prepared_map):
        calls["n"] += 1
        if calls["n"] == 1:
            time.sleep(0.3)
        return {pid: f"result-{pid}" for pid in prepared_map}

    b = BertGlobalBatcher(max_papers=1, batch_fn=slow_first_batch_fn, jobs=jobs)
    t = threading.Thread(target=b.run, daemon=True)
    t.start()
    b.submit("p0", FakePrepared(["s."]))
    b.submit("p1", FakePrepared(["s."]))
    b.end_of_input()
    t.join(timeout=10.0)
    assert not t.is_alive(), "batcher thread did not finish"

    w0 = jobs["p0"].timings["bert_queue_wait"]
    w1 = jobs["p1"].timings["bert_queue_wait"]
    assert 0.0 <= w0 < 0.15, w0  # flushed as soon as it arrived
    assert w1 >= 0.2, w1  # waited through p0's HTTP inside the batcher


def test_bert_queue_wait_stamped_even_when_batch_fails():
    """The stamp happens before batch_fn, so failed batches still carry the
    inbound-wait observation on their (errored) papers."""
    jobs = {"p0": SimpleNamespace(timings={})}

    def failing_batch_fn(prepared_map):
        raise RuntimeError("boom")

    b = BertGlobalBatcher(
        max_papers=1, batch_fn=failing_batch_fn, jobs=jobs, error_fn=lambda pids, err: None
    )
    t = threading.Thread(target=b.run, daemon=True)
    t.start()
    b.submit("p0", FakePrepared(["s."]))
    b.end_of_input()
    t.join(timeout=10.0)
    assert not t.is_alive()
    assert "error" in b.batches[0]
    assert jobs["p0"].timings["bert_queue_wait"] >= 0.0
# ------------------------------------------------ TODO-V07-13: dual-lane mode
#
# endpoint_concurrency=2 submits flushed batches to a batcher-owned
# ThreadPoolExecutor. Invariants under test: in-flight bound, BERT_DONE
# waits for EVERY lane future, submission-order batch_index, out-of-order
# completion correctness, per-batch error isolation. The conc=1 identity
# path is the rest of this file (all Phase 1 tests unchanged).


def test_lanes_end_of_input_waits_for_both_inflight_futures():
    # conc=2: two batches in flight, BOTH unreleased -> run() must not return
    # on END_OF_INPUT; releasing one lane is still not enough.
    gates = {"p0": threading.Event(), "p1": threading.Event()}
    entered = {p: threading.Event() for p in gates}

    def gated_batch_fn(prepared_map):
        (pid,) = prepared_map.keys()
        entered[pid].set()
        gates[pid].wait(timeout=5.0)
        return {pid: f"r-{pid}" for pid in prepared_map}

    b, calls = make_batcher(max_papers=1, batch_fn=gated_batch_fn, endpoint_concurrency=2)
    t = threading.Thread(target=b.run, daemon=True)
    t.start()
    b.submit("p0", FakePrepared(["s."]))
    b.submit("p1", FakePrepared(["s."]))
    assert entered["p0"].wait(timeout=2.0) and entered["p1"].wait(timeout=2.0)
    b.end_of_input()
    assert t.is_alive(), "run() returned with both lane futures in flight"
    gates["p0"].set()  # first lane done, second still parked
    time.sleep(0.1)
    assert t.is_alive(), "run() returned while one lane future was still in flight"
    gates["p1"].set()
    t.join(timeout=2.0)
    assert not t.is_alive()
    assert sorted(pids[0] for pids, _, _ in calls["dispatched"]) == ["p0", "p1"]


def test_lanes_batch_index_monotonic_unique_under_interleaving():
    # 20 one-paper batches through 2 lanes: indices are assigned in the
    # consumer thread at SUBMISSION time, so they must be exactly 0..19 no
    # matter how lane completions interleave (self.batches is completion-order).
    rng_delays = __import__("random").Random(42)

    def jittery_batch_fn(prepared_map):
        time.sleep(rng_delays.uniform(0, 0.02))
        return {pid: f"r-{pid}" for pid in prepared_map}

    b, calls = make_batcher(max_papers=1, batch_fn=jittery_batch_fn, endpoint_concurrency=2)
    papers = [(f"p{i:02d}", FakePrepared(["s."])) for i in range(20)]
    run_sync(b, papers)
    indices = sorted(bt["batch_index"] for bt in b.batches)
    assert indices == list(range(20))


def test_lanes_concurrent_batch_fn_bounded_by_two():
    # Peak simultaneous batch_fn executions must never exceed 2, and with
    # sleepy batches it must actually REACH 2 (lanes truly parallelize).
    lock = threading.Lock()
    state = {"cur": 0, "max": 0}

    def counting_batch_fn(prepared_map):
        with lock:
            state["cur"] += 1
            state["max"] = max(state["max"], state["cur"])
        time.sleep(0.03)
        with lock:
            state["cur"] -= 1
        return {pid: f"r-{pid}" for pid in prepared_map}

    b, calls = make_batcher(max_papers=1, batch_fn=counting_batch_fn, endpoint_concurrency=2)
    papers = [(f"p{i:02d}", FakePrepared(["s."])) for i in range(12)]
    run_sync(b, papers)
    assert state["max"] <= 2, "in-flight HTTP exceeded endpoint_concurrency"
    assert state["max"] == 2, "lanes never ran concurrently"
    assert len(calls["dispatched"]) == 12


def test_lanes_out_of_order_completion_dispatches_correctly():
    # Slow lane takes batch 0 (p0), fast lane finishes batch 1 (p1) first:
    # dispatch order is completion order, but batch_index stays submission
    # order and every paper maps to its own result.
    def staggered_batch_fn(prepared_map):
        (pid,) = prepared_map.keys()
        time.sleep(0.25 if pid == "p0" else 0.01)
        return {pid: f"r-{pid}" for pid in prepared_map}

    b, calls = make_batcher(max_papers=1, batch_fn=staggered_batch_fn, endpoint_concurrency=2)
    t = threading.Thread(target=b.run, daemon=True)
    t.start()
    b.submit("p0", FakePrepared(["s."]))
    time.sleep(0.05)  # p0 is parked in lane 1 before p1 arrives
    b.submit("p1", FakePrepared(["s."]))
    b.end_of_input()
    t.join(timeout=5.0)
    assert not t.is_alive()
    # completion order: p1 finished first
    assert [pids[0] for pids, _, _ in calls["dispatched"]] == ["p1", "p0"]
    # submission-order indices regardless of completion order
    by_pid = {bt["paper_ids"][0]: bt for bt in b.batches}
    assert by_pid["p0"]["batch_index"] == 0
    assert by_pid["p1"]["batch_index"] == 1
    # per-paper results correctly routed
    for pids, results, _stat in calls["dispatched"]:
        assert results == {pids[0]: f"r-{pids[0]}"}


def test_lanes_single_batch_failure_isolated():
    # One lane raises: only that batch's papers hit error_fn; the other lane's
    # batch still dispatches (error isolation survives concurrency).
    def failing_for_p5(prepared_map):
        if "p5" in prepared_map:
            raise ConnectionError("one backend instance down")
        time.sleep(0.02)
        return {pid: f"r-{pid}" for pid in prepared_map}

    b, calls = make_batcher(max_papers=1, batch_fn=failing_for_p5, endpoint_concurrency=2)
    papers = [(f"p{i}", FakePrepared(["s."])) for i in range(8)]
    run_sync(b, papers)
    assert [pids for pids, _ in calls["errors"]] == [["p5"]]
    assert "bert_batch_failed" in calls["errors"][0][1]
    dispatched = sorted(pids[0] for pids, _, _ in calls["dispatched"])
    assert dispatched == [f"p{i}" for i in range(8) if i != 5]
    by_pid = {bt["paper_ids"][0]: bt for bt in b.batches}
    assert "error" in by_pid["p5"]
    assert all("error" not in bt for pid, bt in by_pid.items() if pid != "p5")
