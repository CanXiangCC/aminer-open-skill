"""Chunked-mode bert_batch_monitor.json append-per-window tests (monitor fix P1).

Historical bug: run_bulk runs one scheduler per window under the SAME run_id
and the chunked path overwrote bert_batch_monitor.json each window, so only
the last window's chunk stats survived (Phase 0's "-26%" incident). The writer
now mirrors ``_write_global_batch_monitor``'s read-merge-write append
semantics, and ``_run_chunked_overlap`` offsets chunk_index by the chunks
already on disk (same mechanism as the global batcher's batch_index_start).
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))

import pipeline.production.batch_llm_common as bqc  # noqa: E402
import pipeline.production.config as config_mod  # noqa: E402
from pipeline.production.batch_bert_pipeline_wf4 import (  # noqa: E402
    _SENTINEL,
    BatchBertPipelineSchedulerWf4,
)
from pipeline.production.workflows.spec import get_workflow  # noqa: E402

WF = "prod-wf4-llm-datasets-experiment"
RUN_ID = "chunkedmon/job_batch_000"


def _patch_env(monkeypatch, tmp_path: Path) -> None:
    # The writers import RUNS_DIR inside the function body, so patching the
    # module attribute is enough (same precedent as test_staged_pipeline._Env).
    monkeypatch.setattr(config_mod, "RUNS_DIR", tmp_path)


def _make_sched(
    tmp_path: Path,
    pids: list[str],
    *,
    run_id: str = RUN_ID,
    bert_pipeline_batch_size: int = 2,
) -> BatchBertPipelineSchedulerWf4:
    return BatchBertPipelineSchedulerWf4(
        pids,
        {pid: Path("dummy.md") for pid in pids},
        run_id,
        get_workflow(WF),
        bert_pipeline_batch_size=bert_pipeline_batch_size,
        dry_run=True,
    )


def _window_monitor(sched: BatchBertPipelineSchedulerWf4, chunks: list[dict]) -> dict:
    return {
        "pipeline_mode": "chunked_overlap",
        "chunks": chunks,
        "chunk_count": len(chunks),
        "bert_pipeline_batch_size": sched.bert_pipeline_batch_size,
        "sum_chunk_bert_sec": round(sum(c.get("bert_client_sec", 0.0) for c in chunks), 4),
    }


def _chunk_stat(chunk_index: int, paper_ids: list[str], bert_client_sec: float) -> dict:
    return {
        "chunk_index": chunk_index,
        "paper_ids": list(paper_ids),
        "paper_count": len(paper_ids),
        "prepared_count": len(paper_ids),
        "missing_prep_count": 0,
        "prep_sec": 0.0,
        "prep_wait_sec": 0.0,
        "bert_client_sec": bert_client_sec,
        "bert_started_at": "2026-08-21T00:00:00+00:00",
        "bert_finished_at": "2026-08-21T00:00:01+00:00",
    }


def _read_monitor(tmp_path: Path, run_id: str = RUN_ID) -> dict:
    return json.loads(
        (tmp_path / run_id / "bert_batch_monitor.json").read_text(encoding="utf-8")
    )


def test_chunked_monitor_appends_across_windows(tmp_path: Path, monkeypatch) -> None:
    """Two writer calls (one per run_bulk window, same run_id) must accumulate,
    not overwrite. The second window's chunk_index arrives pre-offset by the
    scheduler (chunk_base mechanism), so the file indices stay unique."""
    _patch_env(monkeypatch, tmp_path)
    sched = _make_sched(tmp_path, ["p1", "p2"])

    sched._write_chunked_batch_monitor(
        _window_monitor(sched, [_chunk_stat(0, ["p1"], 1.0), _chunk_stat(1, ["p2"], 2.0)])
    )
    sched._write_chunked_batch_monitor(_window_monitor(sched, [_chunk_stat(2, ["p3"], 3.0)]))

    d = _read_monitor(tmp_path)
    assert d["pipeline_mode"] == "chunked_overlap"
    assert [c["chunk_index"] for c in d["chunks"]] == [0, 1, 2]
    assert [c["paper_ids"] for c in d["chunks"]] == [["p1"], ["p2"], ["p3"]]
    assert d["chunk_count"] == 3
    assert d["sum_chunk_bert_sec"] == 6.0
    assert d["window_count"] == 2
    assert d["last_window_at"]
    assert d["run_id"] == RUN_ID and d["workflow_id"] == WF


def test_chunked_monitor_single_window_shape(tmp_path: Path, monkeypatch) -> None:
    """Single window keeps the legacy chunked shape (all pre-fix keys) plus the
    two new additive keys — byte-compatible for old readers."""
    _patch_env(monkeypatch, tmp_path)
    sched = _make_sched(tmp_path, ["p1"])
    sched._write_chunked_batch_monitor(_window_monitor(sched, [_chunk_stat(0, ["p1"], 0.5)]))

    d = _read_monitor(tmp_path)
    for key in (
        "run_id",
        "workflow_id",
        "pipeline_mode",
        "chunks",
        "chunk_count",
        "bert_pipeline_batch_size",
        "sum_chunk_bert_sec",
    ):
        assert key in d, key
    assert d["window_count"] == 1
    assert d["chunk_count"] == 1
    assert d["sum_chunk_bert_sec"] == 0.5


def test_existing_chunked_count_mode_guard(tmp_path: Path, monkeypatch) -> None:
    """_existing_chunked_chunk_count only counts same-mode files: missing file,
    foreign pipeline_mode, and corrupt JSON all read as 0."""
    _patch_env(monkeypatch, tmp_path)
    sched = _make_sched(tmp_path, ["p1"])

    assert sched._existing_chunked_chunk_count() == 0  # no file yet

    (tmp_path / RUN_ID).mkdir(parents=True)
    path = tmp_path / RUN_ID / "bert_batch_monitor.json"
    path.write_text(
        json.dumps(
            {"run_id": RUN_ID, "pipeline_mode": "global_batch", "batches": [{}, {}, {}]}
        ),
        encoding="utf-8",
    )
    assert sched._existing_chunked_chunk_count() == 0  # wrong mode

    path.write_text("{not json", encoding="utf-8")
    assert sched._existing_chunked_chunk_count() == 0  # corrupt

    path.write_text(
        json.dumps(
            {"run_id": RUN_ID, "pipeline_mode": "chunked_overlap", "chunks": [{}, {}]}
        ),
        encoding="utf-8",
    )
    assert sched._existing_chunked_chunk_count() == 2


def test_chunked_two_scheduler_runs_share_run_id(tmp_path: Path, monkeypatch) -> None:
    """End-to-end multi-window semantics: run_bulk creates a NEW scheduler per
    window under the same run_id — two run() calls must leave one accumulated
    file with continuous chunk_index, not just the last window."""
    _patch_env(monkeypatch, tmp_path)
    monkeypatch.setattr(bqc, "finalize_errored", lambda job, **kw: None)  # defensive loop no-op

    def run_window(pids: list[str]) -> None:
        sched = _make_sched(tmp_path, pids)
        made: list[dict] = []

        def fake_bert_chunk(chunk_index: int, chunk_ids: list[str], prep_wait_sec: float = 0.0):
            stat = _chunk_stat(chunk_index, chunk_ids, 0.1)
            made.append(stat)
            return stat

        def drain_qwen() -> None:
            while True:
                if sched.llm_q.get() is _SENTINEL:
                    return

        sched._prep_chunk = lambda chunk_ids: None
        sched._run_bert_chunk = fake_bert_chunk
        sched._qwen_worker = drain_qwen
        sched.run()
        assert sched.batch_monitor["chunks"] == made

    run_window(["w1a", "w1b", "w1c"])  # window 1: 2 chunks (batch_size=2)
    run_window(["w2a"])  # window 2: 1 chunk

    d = _read_monitor(tmp_path)
    assert d["window_count"] == 2
    assert [c["chunk_index"] for c in d["chunks"]] == [0, 1, 2]
    assert [c["paper_ids"] for c in d["chunks"]] == [["w1a", "w1b"], ["w1c"], ["w2a"]]
    assert d["chunk_count"] == 3
