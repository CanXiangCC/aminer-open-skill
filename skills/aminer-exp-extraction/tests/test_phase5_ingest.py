"""Phase 5 ingest tests (TODO-V07-06): CSV order, dedup, classification,
atomic publish, numbering, idempotency. All against tmp dirs; production
manifests are never touched."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))

import pipeline.production.manifest_ingest as mi  # noqa: E402


@pytest.fixture()
def run_ids_env(tmp_path: Path, monkeypatch):
    """Redirect RUNS_DIR to tmp so prediction dedup tests are hermetic."""
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(mi, "RUNS_DIR", runs)
    return runs


def _csv(tmp_path: Path, rows: list[dict], header=("paper_id", "md_url", "publication_id")) -> Path:
    import csv as _csv

    p = tmp_path / "input.csv"
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=list(header))
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return p


def _batch(manifest_dir: Path, idx: int, papers: list[dict]) -> None:
    (manifest_dir / f"job_batch_{idx:03d}.json").write_text(
        json.dumps(
            {
                "job_batch_id": f"job_batch_{idx:03d}",
                "batch_index": idx,
                "size": len(papers),
                "machine": None,
                "machine_index": None,
                "machine_count": None,
                "papers": papers,
            }
        ),
        encoding="utf-8",
    )


def _pred(runs: Path, run_id: str, jid: str, pid: str, error: str | None) -> None:
    d = runs / run_id / jid / "predictions"
    d.mkdir(parents=True, exist_ok=True)
    payload = {"paper_id": pid}
    if error:
        payload["error"] = error
    (d / f"{pid}.json").write_text(json.dumps(payload), encoding="utf-8")


U = "http://oss.example.com/md/{pid}.md"


# --- 1. CSV row order preserved -------------------------------------------

def test_csv_order_preserved(tmp_path: Path):
    rows = [{"paper_id": f"p{i:02d}", "md_url": U.format(pid=f"p{i:02d}")} for i in range(12)]
    report = mi.ingest_csv(_csv(tmp_path, rows), tmp_path / "m", size=10)
    assert report.counts["new"] == 12
    published = sorted(report.published)
    assert published == ["job_batch_000.json", "job_batch_001.json"]
    b0 = json.loads((tmp_path / "m" / published[0]).read_text(encoding="utf-8"))
    b1 = json.loads((tmp_path / "m" / published[1]).read_text(encoding="utf-8"))
    queued = [p["paper_id"] for p in b0["papers"] + b1["papers"]]
    assert queued == [f"p{i:02d}" for i in range(12)]  # original CSV order kept
    assert len(b0["papers"]) == 10 and len(b1["papers"]) == 2


# --- 2/3. dedup: CSV-internal, against existing manifest -------------------

def test_internal_csv_dedup(tmp_path: Path):
    rows = [
        {"paper_id": "a", "md_url": U.format(pid="a")},
        {"paper_id": "a", "md_url": U.format(pid="a")},  # exact internal dup
    ]
    report = mi.ingest_csv(_csv(tmp_path, rows), tmp_path / "m")
    assert report.counts == {"new": 1, "duplicate": 1, "invalid": 0, "retry": 0, "conflict": 0}
    dup = [r for r in report.rows if r.status == "duplicate"][0]
    assert dup.line_no == 3 and "csv" in dup.reason


def test_dedup_against_existing_manifest(tmp_path: Path):
    m = tmp_path / "m"
    m.mkdir()
    _batch(m, 0, [{"paper_id": "a", "md_url": U.format(pid="a")}])
    rows = [
        {"paper_id": "a", "md_url": U.format(pid="a")},           # same pid
        {"paper_id": "zz", "md_url": U.format(pid="a")},          # same url, new pid -> conflict
        {"paper_id": "b", "md_url": U.format(pid="b")},           # genuinely new
    ]
    report = mi.ingest_csv(_csv(tmp_path, rows), m)
    assert report.counts["new"] == 1
    assert report.counts["duplicate"] == 1
    assert report.counts["conflict"] == 1
    # url-only dup (different pid, url owned by nobody) is a conflict, never silent
    conflict = [r for r in report.rows if r.status == "conflict"][0]
    assert conflict.reason


def test_dedup_url_normalization(tmp_path: Path):
    m = tmp_path / "m"
    m.mkdir()
    _batch(m, 0, [{"paper_id": "a", "md_url": "http://OSS.Example.com/md/a.md/"}])
    rows = [{"paper_id": "zz", "md_url": "http://oss.example.com/md/a.md"}]
    report = mi.ingest_csv(_csv(tmp_path, rows), m)
    # host case + trailing slash normalized -> same url identity -> conflict (different pid)
    assert report.counts["conflict"] == 1 and report.counts["new"] == 0


# --- 4/5. prediction dedup + retry gating ----------------------------------

def test_dedup_against_success_prediction(tmp_path: Path, run_ids_env: Path):
    _pred(run_ids_env, "r1", "job_batch_000", "a", error=None)
    _pred(run_ids_env, "r1", "job_batch_000", "e", error="llm/post: boom")
    rows = [
        {"paper_id": "a", "md_url": U.format(pid="a")},  # ok prediction -> duplicate
        {"paper_id": "e", "md_url": U.format(pid="e")},  # error prediction -> retry
        {"paper_id": "n", "md_url": U.format(pid="n")},  # new
    ]
    report = mi.ingest_csv(_csv(tmp_path, rows), tmp_path / "m", run_ids=["r1"])
    assert report.counts["duplicate"] == 1
    assert report.counts["retry"] == 1
    assert report.counts["new"] == 1
    batch = json.loads((tmp_path / "m" / "job_batch_000.json").read_text(encoding="utf-8"))
    assert [p["paper_id"] for p in batch["papers"]] == ["n"]  # retry NOT queued by default


def test_error_prediction_only_queued_with_include_retry(tmp_path: Path, run_ids_env: Path):
    _pred(run_ids_env, "r1", "job_batch_000", "e", error="llm/post: boom")
    rows = [{"paper_id": "e", "md_url": U.format(pid="e")}]
    report = mi.ingest_csv(_csv(tmp_path, rows), tmp_path / "m", run_ids=["r1"], include_retry=True)
    assert report.counts["retry"] == 1
    batch = json.loads((tmp_path / "m" / "job_batch_000.json").read_text(encoding="utf-8"))
    assert [p["paper_id"] for p in batch["papers"]] == ["e"]


# --- 6. invalid rows keep line number + reason ------------------------------

def test_invalid_rows_keep_line_no_and_reason(tmp_path: Path):
    rows = [
        {"paper_id": "ok", "md_url": U.format(pid="ok")},
        {"paper_id": "nourl", "md_url": ""},
        {"paper_id": "", "md_url": U.format(pid="x")},  # no id anywhere
        {"paper_id": "bad", "md_url": "not-a-url"},
    ]
    report = mi.ingest_csv(_csv(tmp_path, rows), tmp_path / "m")
    invalid = sorted((r.line_no, r.reason) for r in report.rows if r.status == "invalid")
    assert [ln for ln, _ in invalid] == [3, 4, 5]
    assert any("missing md_url" in rs for _, rs in invalid)
    assert any("paper_id" in rs for _, rs in invalid)
    assert any("scheme" in rs for _, rs in invalid)


def test_ai2000_has_md_style_csv(tmp_path: Path):
    """id,has_md,md_url layout (data/ai2000_has_md_ids.csv): has_md=0 -> invalid."""
    rows = [
        {"id": "i1", "md_url": U.format(pid="i1")},
        {"id": "i2", "md_url": ""},
    ]
    report = mi.ingest_csv(_csv(tmp_path, rows, header=("id", "md_url")), tmp_path / "m")
    assert report.counts["new"] == 1 and report.counts["invalid"] == 1
    batch = json.loads((tmp_path / "m" / "job_batch_000.json").read_text(encoding="utf-8"))
    assert batch["papers"][0]["paper_id"] == "i1"  # id column used as paper_id


# --- 7/8. batch numbering never collides ------------------------------------

def test_batch_numbering_monotonic_no_reuse(tmp_path: Path):
    m = tmp_path / "m"
    m.mkdir()
    _batch(m, 0, [{"paper_id": "a", "md_url": U.format(pid="a")}])
    _batch(m, 2, [{"paper_id": "c", "md_url": U.format(pid="c")}])  # gap at 1
    rows = [{"paper_id": f"n{i}", "md_url": U.format(pid=f"n{i}")} for i in range(3)]
    mi.ingest_csv(_csv(tmp_path, rows), m)
    assert (m / "job_batch_003.json").exists()  # next = max(0,2)+1
    rows2 = [{"paper_id": f"z{i}", "md_url": U.format(pid=f"z{i}")} for i in range(3)]
    mi.ingest_csv(_csv(tmp_path, rows2), m, size=2)
    assert (m / "job_batch_004.json").exists() and (m / "job_batch_005.json").exists()


# --- 9/10/17. atomic publish + no half-published file on failure -------------

def test_atomic_publish_uses_tmp_and_replace(tmp_path: Path, monkeypatch):
    m = tmp_path / "m"
    replaced: list[Path] = []
    real_replace = mi.os.replace
    monkeypatch.setattr(mi.os, "replace", lambda a, b: (replaced.append((Path(a), Path(b))), real_replace(a, b))[1])
    rows = [{"paper_id": "a", "md_url": U.format(pid="a")}]
    mi.ingest_csv(_csv(tmp_path, rows), m)
    assert replaced and replaced[0][0].name == "job_batch_000.json.tmp"
    assert replaced[0][1].name == "job_batch_000.json"
    assert not list(m.glob("*.tmp"))
    data = json.loads((m / "job_batch_000.json").read_text(encoding="utf-8"))  # valid JSON published
    assert data["papers"][0]["paper_id"] == "a"
    assert data["ingest"]["row_count"] == 1


def test_failed_publish_leaves_no_half_file(tmp_path: Path, monkeypatch):
    m = tmp_path / "m"

    def boom(path: Path, payload: dict):
        raise OSError("disk full")

    monkeypatch.setattr(mi, "_write_json_atomic", boom)
    rows = [{"paper_id": "a", "md_url": U.format(pid="a")}]
    with pytest.raises(OSError):
        mi.ingest_csv(_csv(tmp_path, rows), m)
    assert not list(m.glob("job_batch_*.json"))
    assert not list(m.glob("*.tmp"))


def test_existing_batch_never_modified(tmp_path: Path):
    m = tmp_path / "m"
    m.mkdir()
    _batch(m, 0, [{"paper_id": "a", "md_url": U.format(pid="a")}])
    before = (m / "job_batch_000.json").read_bytes()
    rows = [{"paper_id": "b", "md_url": U.format(pid="b")}]
    mi.ingest_csv(_csv(tmp_path, rows), m)
    assert (m / "job_batch_000.json").read_bytes() == before  # untouched


def test_concurrent_reader_never_sees_half_json(tmp_path: Path, monkeypatch):
    """Between tmp write and os.replace the reader sees nothing, never garbage."""
    m = tmp_path / "m"
    m.mkdir()
    seen: list[str | None] = []

    real_replace = mi.os.replace
    from pipeline.production.manifest_ingest import _write_json_atomic

    def spying_replace(a, b):
        target = Path(b)
        seen.append(target.read_text(encoding="utf-8") if target.exists() else None)
        return real_replace(a, b)

    monkeypatch.setattr(mi.os, "replace", spying_replace)
    rows = [{"paper_id": "a", "md_url": U.format(pid="a")}]
    mi.ingest_csv(_csv(tmp_path, rows), m)
    assert seen == [None]  # before replace the file simply does not exist


# --- 11. idempotency ---------------------------------------------------------

def test_double_ingest_same_csv_idempotent(tmp_path: Path):
    rows = [{"paper_id": f"p{i}", "md_url": U.format(pid=f"p{i}")} for i in range(3)]
    csv_path = _csv(tmp_path, rows)
    r1 = mi.ingest_csv(csv_path, tmp_path / "m")
    r2 = mi.ingest_csv(csv_path, tmp_path / "m")
    assert r1.counts["new"] == 3 and r2.counts["new"] == 0
    assert r2.counts["duplicate"] == 3
    assert r2.published == []  # no new batch, nothing published
    assert len(list((tmp_path / "m").glob("job_batch_*.json"))) == 1


# --- ingest metadata ---------------------------------------------------------

def test_ingest_metadata_in_batch(tmp_path: Path):
    rows = [{"paper_id": "a", "md_url": U.format(pid="a")}, {"paper_id": "", "md_url": ""}]
    report = mi.ingest_csv(_csv(tmp_path, rows), tmp_path / "m", source_name="lilaoshi2")
    batch = json.loads((tmp_path / "m" / "job_batch_000.json").read_text(encoding="utf-8"))
    meta = batch["ingest"]
    assert meta["source_name"] == "lilaoshi2"
    assert meta["row_count"] == 2 and meta["new_count"] == 1 and meta["invalid_count"] == 1
    assert meta["csv_sha256"] == report.csv_sha256
    ledger = [json.loads(l) for l in (tmp_path / "m" / mi.LEDGER_NAME).read_text().splitlines() if l.strip()]
    assert len(ledger) == 1 and ledger[0]["ingest_id"] == report.ingest_id


if __name__ == "__main__":
    raise SystemExit("run via pytest")
