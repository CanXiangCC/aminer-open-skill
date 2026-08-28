"""Completion ledger (TODO-V07-11 c1) — append semantics + resume fallback.

Covers:
  1. append/read roundtrip with full row shape (sha256 over payload bytes)
  2. last-row-wins semantics (ok->error retries, error->ok recovers)
  3. prediction_ok fallback matrix: file authoritative when present;
     ledger decides only when the file is absent/unreadable
  4. commit_paper_finalization appends the row AFTER the prediction is
     durably published (ok and error paths)
  5. stat-keyed index cache invalidates on append
  6. concurrent appends (window-mode multi-threaded commit) stay
     line-atomic
"""

from __future__ import annotations

import hashlib
import json
import sys
import threading
from pathlib import Path

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))

import pipeline.production.config as config_mod  # noqa: E402
import pipeline.production.monitor as monitor_mod  # noqa: E402
import pipeline.production.post_llm as post_llm  # noqa: E402
import pipeline.production.run_paths as run_paths  # noqa: E402
from pipeline.production import completion_ledger as cl  # noqa: E402
from pipeline.production.post_llm import PaperFinalization  # noqa: E402

SESSION = "ledg1"
RUN_ID = f"{SESSION}/job_batch_000"


class _Env:
    """Point every filesystem-writing module at tmp_path."""

    def __init__(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setattr(post_llm, "RUNS_DIR", tmp_path)
        monkeypatch.setattr(run_paths, "RUNS_DIR", tmp_path)
        monkeypatch.setattr(config_mod, "RUNS_DIR", tmp_path)
        monkeypatch.setattr(config_mod, "PARTIALS_DIR", tmp_path / "partials")
        monkeypatch.setattr(monitor_mod, "RUN_HISTORY_PATH", tmp_path / "history.jsonl")
        monkeypatch.setenv("PROD_SKIP_PAPER_MONITOR", "1")
        cl.reset_cache()


def _append(status: str = "ok", pid: str = "p1", payload: str = '{"paper_id": "p1"}') -> dict:
    return cl.append_row(
        SESSION,
        "job_batch_000",
        RUN_ID,
        pid,
        status,
        error_class="llm_timeout" if status == "error" else None,
        experiments=2 if status == "ok" else 0,
        prediction_payload=payload,
        workflow_version="0.7.0",
    )


def test_append_read_roundtrip(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    row = _append()
    rows = cl.read_rows(SESSION)
    assert len(rows) == 1
    assert rows[0] == row
    assert row["session_run_id"] == SESSION
    assert row["job_batch_id"] == "job_batch_000"
    assert row["run_id"] == RUN_ID
    assert row["paper_id"] == "p1"
    assert row["status"] == "ok"
    assert row["experiments"] == 2
    assert row["workflow_version"] == "0.7.0"
    assert "error_class" not in row
    assert row["prediction_sha256"] == hashlib.sha256(
        '{"paper_id": "p1"}'.encode("utf-8")
    ).hexdigest()
    assert row["ts"]


def test_last_row_wins(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    assert cl.ledger_ok(SESSION, "p1") is False  # no ledger yet
    _append("ok")
    assert cl.ledger_ok(SESSION, "p1") is True
    _append("error", pid="p1")  # e.g. --force rerun that errored
    assert cl.ledger_ok(SESSION, "p1") is False
    _append("ok", pid="p1")  # error retry recovered
    assert cl.ledger_ok(SESSION, "p1") is True
    idx = cl.last_status_index(SESSION)
    assert idx == {"p1": "ok"}


def test_error_row_shape(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    _append("error")
    row = cl.read_rows(SESSION)[0]
    assert row["status"] == "error"
    assert row["error_class"] == "llm_timeout"
    assert row["experiments"] == 0
    assert cl.ledger_ok(SESSION, "p1") is False


def test_prediction_ok_fallback_matrix(tmp_path: Path, monkeypatch) -> None:
    env = _Env(monkeypatch, tmp_path)
    ok = lambda pid: run_paths.prediction_ok(SESSION, "job_batch_000", pid)  # noqa: E731

    assert ok("p1") is False  # file + ledger both absent -> retry

    _append("ok", pid="p1")
    assert ok("p1") is True  # file absent, ledger ok -> skip (compacted)

    # File with error marker is authoritative even with an ok ledger row.
    pred_dir = tmp_path / SESSION / "job_batch_000" / "predictions"
    pred_dir.mkdir(parents=True)
    (pred_dir / "p1.json").write_text(
        json.dumps({"paper_id": "p1", "experiments": [], "error": "llm_timeout"}),
        encoding="utf-8",
    )
    assert ok("p1") is False

    # File ok without any ledger row keeps working (legacy runs).
    (pred_dir / "p2.json").write_text(
        json.dumps({"paper_id": "p2", "experiments": []}), encoding="utf-8"
    )
    assert ok("p2") is True

    # Corrupt file falls back to the ledger.
    (pred_dir / "p3.json").write_text("{not json", encoding="utf-8")
    _append("ok", pid="p3")
    assert ok("p3") is True
    assert env is not None


def _fin(tmp_path: Path, pid: str, error: str | None = None) -> PaperFinalization:
    pred = {
        "paper_id": pid,
        "run_id": RUN_ID,
        "workflow_id": "prod-wf4-llm-datasets-experiment",
        "workflow_version": "0.7.0",
        "experiments": [] if error else [{"experiment_name": "E1"}, {"experiment_name": "E2"}],
    }
    if error:
        pred["error"] = error
    base = tmp_path / RUN_ID / "predictions"
    return PaperFinalization(
        paper_id=pid,
        run_id=RUN_ID,
        workflow_id=pred["workflow_id"],
        dry_run=False,
        prediction=pred,
        monitor={"paper_id": pid},
        pred_path=base / f"{pid}.json",
        mon_path=base.parent / "monitors" / f"{pid}_monitor.json",
        experiments=pred["experiments"],
        provenance=[],
        error=error,
    )


def test_commit_appends_ledger_row(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)

    post_llm.commit_paper_finalization(_fin(tmp_path, "pa"))
    rows = cl.read_rows(SESSION)
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "ok"
    assert row["experiments"] == 2
    # Row lands only after the prediction is durably published, and its
    # sha256 matches the committed file byte-for-byte.
    f = tmp_path / RUN_ID / "predictions" / "pa.json"
    assert f.exists()
    assert row["prediction_sha256"] == hashlib.sha256(f.read_bytes()).hexdigest()
    assert row["workflow_version"] == "0.7.0"

    post_llm.commit_paper_finalization(_fin(tmp_path, "pb", error="bert_batch_failed: x"))
    row_b = cl.read_rows(SESSION)[-1]
    assert row_b["paper_id"] == "pb"
    assert row_b["status"] == "error"
    assert row_b["error_class"] == "bert_batch_failed: x"
    assert run_paths.prediction_ok(SESSION, "job_batch_000", "pa") is True
    assert run_paths.prediction_ok(SESSION, "job_batch_000", "pb") is False


def test_commit_dry_run_skips_ledger(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    fin = _fin(tmp_path, "pd")
    fin.dry_run = True
    post_llm.commit_paper_finalization(fin)
    assert cl.read_rows(SESSION) == []


def test_cache_invalidates_on_append(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    assert cl.ledger_ok(SESSION, "p1") is False  # seeds the (empty) cache
    _append("ok", pid="p1")
    assert cl.ledger_ok(SESSION, "p1") is True  # stat key changed -> re-read


def test_concurrent_appends_line_atomic(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    errs: list[Exception] = []

    def worker(w: int) -> None:
        try:
            for i in range(25):
                cl.append_row(
                    SESSION, "job_batch_000", RUN_ID, f"p{w}-{i}", "ok",
                    prediction_payload="{}", workflow_version="0.7.0",
                )
        except Exception as exc:  # noqa: BLE001
            errs.append(exc)

    threads = [threading.Thread(target=worker, args=(w,)) for w in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errs == []
    lines = cl.ledger_path(SESSION).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 200
    rows = [json.loads(x) for x in lines]
    assert {r["paper_id"] for r in rows} == {f"p{w}-{i}" for w in range(8) for i in range(25)}


if __name__ == "__main__":
    raise SystemExit("run via pytest")
