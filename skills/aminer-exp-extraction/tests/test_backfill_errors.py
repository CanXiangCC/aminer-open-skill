"""Tests for scripts/backfill_errors.py (post-v0.7.0 plan Part 4 c1)."""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest

PROD_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PROD_ROOT / "scripts"


def _load(name: str) -> object:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / "backfill_errors.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_pred(runs: Path, session: str, pid: str, kind: str) -> None:
    d = runs / session / "job_batch_000" / "predictions"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{pid}.json"
    if kind == "missing":
        return
    if kind == "ok":
        p.write_text(json.dumps({"paper_id": pid, "experiments": [{"experiment_name": "e"}]}),
                     encoding="utf-8")
    elif kind == "error":
        p.write_text(json.dumps({"paper_id": pid, "error": "parse_error: bad json"}),
                     encoding="utf-8")
    elif kind == "corrupt":
        p.write_text("not-json{", encoding="utf-8")


def _write_monitor(runs: Path, session: str, pid: str) -> None:
    """Monitor-only trace: prediction+monitor committed but progress write lost."""
    d = runs / session / "job_batch_000" / "monitors"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{pid}_monitor.json").write_text(json.dumps({"paper_id": pid}), encoding="utf-8")


def _write_progress(runs: Path, session: str, rows: list[dict]) -> None:
    d = runs / session / "job_batch_000"
    d.mkdir(parents=True, exist_ok=True)
    with (d / "progress.jsonl").open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _row(session: str, pid: str, status: str, error: str | None = None) -> dict:
    return {"ts": "2026-08-21T00:00:00Z", "run_id": f"{session}/job_batch_000",
            "session_run_id": session, "job_batch_id": "job_batch_000",
            "paper_id": pid, "status": status, "error": error,
            "llm_elapsed_sec": 1.0}


def _mk_index(root: Path, pid_urls: dict[str, str]) -> Path:
    corpus = root / "corpus_a"
    corpus.mkdir(parents=True, exist_ok=True)
    (corpus / "job_batch_000.json").write_text(json.dumps({
        "job_batch_id": "job_batch_000", "batch_index": 0, "size": len(pid_urls),
        "papers": [{"paper_id": p, "md_url": u} for p, u in pid_urls.items()]}),
        encoding="utf-8")
    return root


URLS = {f"p{i}": f"http://example.com/{i}.md" for i in range(10)}


@pytest.fixture()
def env(tmp_path: Path):
    runs = tmp_path / "runs"
    mroot = _mk_index(tmp_path / "manifests", URLS)
    return runs, mroot


def test_error_set_derivation_all_classes(env, tmp_path: Path) -> None:
    mod = _load("bf1")
    runs, mroot = env
    s = "sess-derive"
    _write_pred(runs, s, "p0", "ok")
    _write_pred(runs, s, "p1", "error")                       # error_marker -> parse_error
    _write_pred(runs, s, "p2", "corrupt")
    _write_pred(runs, s, "p3", "missing")                     # progress ok -> missing_prediction
    _write_pred(runs, s, "p4", "missing")                     # monitor-only trace, no progress
    _write_pred(runs, s, "p5", "missing")                     # progress md_fetch -> excluded
    _write_pred(runs, s, "p6", "missing")                     # progress llm_timeout -> included
    _write_monitor(runs, s, "p4")
    _write_progress(runs, s, [
        _row(s, "p0", "ok"), _row(s, "p1", "ok"), _row(s, "p3", "ok"),
        _row(s, "p5", "error", "md fetch failed: 404"),
        _row(s, "p6", "error", "llm timeout after 30s"),
    ])
    rep = mod.analyze_run(s, runs, mod.build_md_url_index(mroot)[0])
    assert rep["ok_count"] == 1
    assert rep["included"]["parse_error"] == ["p1"]
    assert rep["included"]["corrupt"] == ["p2"]
    assert rep["included"]["missing_prediction"] == ["p3", "p4"]
    assert rep["included"]["llm_timeout"] == ["p6"]
    assert rep["excluded"] == {"md_fetch": 1}
    assert rep["backfill_papers"] == ["p1", "p2", "p3", "p4", "p6"]


def test_include_md_fetch_flag(env) -> None:
    mod = _load("bf2")
    runs, mroot = env
    s = "sess-mdf"
    _write_pred(runs, s, "p0", "missing")
    _write_progress(runs, s, [_row(s, "p0", "error", "md fetch failed: 404")])
    idx = mod.build_md_url_index(mroot)[0]
    assert mod.analyze_run(s, runs, idx)["excluded"] == {"md_fetch": 1}
    rep = mod.analyze_run(s, runs, idx, include_md_fetch=True)
    assert rep["included"].get("md_fetch") == ["p0"]
    assert rep["backfill_papers"] == ["p0"]


def test_ledger_ok_excludes_missing_file(env) -> None:
    mod = _load("bf3")
    runs, mroot = env
    s = "sess-ledger"
    _write_pred(runs, s, "p0", "missing")
    _write_pred(runs, s, "p1", "missing")
    _write_progress(runs, s, [_row(s, "p0", "ok"), _row(s, "p1", "ok")])
    (runs / s / "ledger.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (runs / s / "ledger.jsonl").write_text(
        json.dumps({"paper_id": "p0", "status": "ok"}) + "\n"
        + json.dumps({"paper_id": "p1", "status": "error"}) + "\n",
        encoding="utf-8")
    rep = mod.analyze_run(s, runs, mod.build_md_url_index(mroot)[0])
    assert rep["excluded"].get("ledger_ok") == 1
    assert rep["included"]["missing_prediction"] == ["p1"]  # ledger error -> still backfill


def test_no_md_url_paper_skipped_and_warned(env, capsys) -> None:
    mod = _load("bf4")
    runs, mroot = env
    s = "sess-nourl"
    _write_pred(runs, s, "p0", "missing")   # p0 in index
    _write_pred(runs, s, "pX", "missing")   # pX NOT in index
    _write_progress(runs, s, [_row(s, "p0", "ok"), _row(s, "pX", "ok")])
    rc = mod.main(["--run-id", s, "--runs-dir", str(runs),
                   "--source-manifest-dir", str(mroot)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "WARN no md_url" in out and "pX" in out
    assert not (mroot / "backfill").exists()  # dry-run default: zero writes


def test_dry_run_default_zero_writes(env, capsys) -> None:
    mod = _load("bf5")
    runs, mroot = env
    s = "sess-dry"
    _write_pred(runs, s, "p0", "error")
    rc = mod.main(["--run-id", s, "--runs-dir", str(runs),
                   "--source-manifest-dir", str(mroot)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "dry-run, NOT written" in out
    assert "projected (0+1)/1" in out
    assert not (mroot / "backfill").exists()
    assert not list(mroot.rglob("*.json.tmp"))


def test_durable_rate_computation(env) -> None:
    mod = _load("bf6")
    runs, mroot = env
    s = "sess-rate"
    for i in range(4):
        _write_pred(runs, s, f"p{i}", "ok")
    _write_pred(runs, s, "p4", "missing")
    _write_pred(runs, s, "p5", "error")
    _write_progress(runs, s, [_row(s, f"p{i}", "ok") for i in range(6)])
    rep = mod.analyze_run(s, runs, mod.build_md_url_index(mroot)[0])
    assert rep["durable_before"] == pytest.approx(4 / 6)
    assert rep["durable_after_projected"] == pytest.approx(6 / 6)


def test_apply_writes_manifest_and_meta(env) -> None:
    mod = _load("bf7")
    runs, mroot = env
    s = "sess-apply"
    _write_pred(runs, s, "p0", "error")
    _write_pred(runs, s, "p1", "missing")
    _write_progress(runs, s, [_row(s, "p0", "ok"), _row(s, "p1", "ok")])
    rc = mod.main(["--run-id", s, "--apply", "--runs-dir", str(runs),
                   "--source-manifest-dir", str(mroot)])
    assert rc == 0
    dirs = list((mroot / "backfill").iterdir())
    assert len(dirs) == 1 and dirs[0].name.startswith(f"{s}-")
    data = json.loads((dirs[0] / "job_batch_backfill_000.json").read_text(encoding="utf-8"))
    assert data["job_batch_id"] == "job_batch_backfill_000"
    assert data["size"] == 2
    assert {p["paper_id"] for p in data["papers"]} == {"p0", "p1"}
    assert all(p["md_url"].startswith("http://example.com/") for p in data["papers"])
    meta = json.loads((dirs[0] / "backfill_meta.json").read_text(encoding="utf-8"))
    assert meta["source_run_ids"] == [s] and meta["papers"] == 2
    assert "guardrail" in meta
    assert not list((mroot / "backfill").rglob("*.tmp"))


def test_manifest_readable_by_run_bulk(env) -> None:
    mod = _load("bf8")
    runs, mroot = env
    s = "sess-readable"
    _write_pred(runs, s, "p0", "error")
    mod.main(["--run-id", s, "--apply", "--runs-dir", str(runs),
              "--source-manifest-dir", str(mroot)])
    bf_dir = list((mroot / "backfill").iterdir())[0]
    spec = importlib.util.spec_from_file_location("bf_rb", SCRIPTS / "run_bulk.py")
    rb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rb)
    paths = rb._list_job_batches(bf_dir, None)
    assert len(paths) == 1 and paths[0].name == "job_batch_backfill_000.json"
    jid, papers = rb._load_job_batch(paths[0])
    assert jid == "job_batch_backfill_000"
    assert papers and papers[0]["paper_id"] == "p0" and papers[0]["md_url"]


def test_run_flag_invokes_run_bulk_subprocess(env, monkeypatch, capsys) -> None:
    mod = _load("bf9")
    runs, mroot = env
    s = "sess-runflag"
    _write_pred(runs, s, "p0", "missing")
    _write_progress(runs, s, [_row(s, "p0", "ok")])
    calls: list[list[str]] = []
    monkeypatch.setattr(mod.subprocess, "run",
                        lambda cmd, **kw: calls.append(cmd) or type("R", (), {"returncode": 0})())
    rc = mod.main(["--run-id", s, "--new-run-id", f"{s}-bf-test", "--run",
                   "--runs-dir", str(runs), "--source-manifest-dir", str(mroot)])
    assert rc == 0 and len(calls) == 1
    cmd = calls[0]
    assert cmd[1].endswith("run_bulk.py")
    assert "--run-id" in cmd and cmd[cmd.index("--run-id") + 1] == f"{s}-bf-test"
    bf_dir = cmd[cmd.index("--manifest-dir") + 1]
    assert Path(bf_dir).is_dir() and (Path(bf_dir) / "job_batch_backfill_000.json").exists()
    out = capsys.readouterr().out
    assert "never enters official merges" in out or "never merged into official" in out


def test_default_new_run_id() -> None:
    mod = _load("bf10")
    today = time.strftime("%Y%m%d")
    assert mod.default_new_run_id(["abc-20260821"]) == f"abc-20260821-bf{today}"


def test_md_url_conflict_prefers_https(tmp_path: Path) -> None:
    """Same OSS object re-published (old http path vs new https path, seen for
    64702dee... across lilaoshi corpora): https variant must win."""
    mod = _load("bf11")
    root = tmp_path / "manifests"
    for corpus, url in (("a_first", "http://oss/2025/old.md"),
                        ("b_second", "https://oss/2026/new.md")):
        d = root / corpus
        d.mkdir(parents=True)
        (d / "job_batch_000.json").write_text(json.dumps({
            "job_batch_id": "job_batch_000", "batch_index": 0, "size": 1,
            "papers": [{"paper_id": "p0", "md_url": url}]}), encoding="utf-8")
    index, conflicts = mod.build_md_url_index(root)
    assert conflicts == 1
    assert index["p0"] == "https://oss/2026/new.md"
