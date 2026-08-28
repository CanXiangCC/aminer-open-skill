"""TODO-V07-10 Part 2: ai2000 corpus builder tests.

Covers scripts/build_ai2000_manifests.py (see docs/V07_ROLLING_REFILL_PLAN_20260821.md §2):
  - CSV contract: missing columns / has_md=0 / empty URL / duplicate candidate id
  - deterministic nested selection (fixed seed reproducible, p256 ⊂ p500,
    lilaoshi exclusion replenished from the candidate tail, zero intersection,
    insufficient candidates fail clearly)
  - manifest write: p160single schema, size/order verbatim, atomic publish
    (no .tmp residue), returned sha256 matches file bytes
  - derived md-only CSV shape
  - production-path URL probe: success / empty body / HTTP error via
    monkeypatched ensure_cached
  - main() end-to-end on tmp paths (offline, --skip-probe)
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))

_spec = importlib.util.spec_from_file_location(
    "build_ai2000_manifests", PROD_ROOT / "scripts" / "build_ai2000_manifests.py"
)
build_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_mod)


def _write_ids_csv(path: Path, rows: list[tuple[str, str, str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "has_md", "md_url"])
        w.writerows(rows)
    return path


def _candidate_rows(n: int, prefix: str = "ai") -> list[tuple[str, str, str]]:
    return [(f"{prefix}{i:03d}", "1", f"https://md.example/{prefix}{i:03d}.md") for i in range(n)]


# ----------------------------------------------------------------- CSV contract


def test_read_rows_filters_and_rejects_bad_input(tmp_path: Path) -> None:
    # has_md=0 and empty URL are filtered, has_md=1 kept verbatim
    src = _write_ids_csv(
        tmp_path / "ids.csv",
        [
            ("a1", "0", "https://x/1.md"),
            ("a2", "1", "https://x/2.md"),
            ("a3", "1", ""),
            ("", "1", "https://x/4.md"),
            ("a5", "1", "https://x/5.md"),
        ],
    )
    rows, stats = build_mod.read_ai2000_rows(src)
    assert [r["paper_id"] for r in rows] == ["a2", "a5"]
    assert stats["total"] == 5 and stats["has_md"] == 4 and stats["kept"] == 2
    assert stats["dropped_no_url"] == 2

    # missing columns -> clear error
    bad = tmp_path / "bad.csv"
    bad.write_text("id,url\na1,u\n", encoding="utf-8")
    try:
        build_mod.read_ai2000_rows(bad)
        raise AssertionError("expected CorpusError for missing columns")
    except build_mod.CorpusError as exc:
        assert "missing columns" in str(exc)

    # duplicate candidate id -> source-integrity error
    dup = _write_ids_csv(
        tmp_path / "dup.csv", [("a1", "1", "https://x/1.md"), ("a1", "1", "https://x/1b.md")]
    )
    try:
        build_mod.read_ai2000_rows(dup)
        raise AssertionError("expected CorpusError for duplicate id")
    except build_mod.CorpusError as exc:
        assert "duplicate" in str(exc)


# -------------------------------------------------------------------- selection


def test_select_nested_deterministic_and_nested(tmp_path: Path) -> None:
    src = _write_ids_csv(tmp_path / "ids.csv", _candidate_rows(40))
    rows, _ = build_mod.read_ai2000_rows(src)

    sel_a, inner_a, stats_a = build_mod.select_nested(
        rows, set(), seed=7, n=10, inner=5
    )
    sel_b, inner_b, _ = build_mod.select_nested(rows, set(), seed=7, n=10, inner=5)
    # same seed -> byte-identical selection
    assert sel_a == sel_b and inner_a == inner_b
    # inner is a strict prefix/subset of n; no duplicates
    ids_a = [r["paper_id"] for r in sel_a]
    assert len(set(ids_a)) == 10
    assert {r["paper_id"] for r in inner_a} < set(ids_a)
    assert stats_a["candidates"] == 40

    # different seed -> (almost surely) different selection; nesting still holds
    sel_c, inner_c, _ = build_mod.select_nested(rows, set(), seed=8, n=10, inner=5)
    assert [r["paper_id"] for r in sel_c] != ids_a
    assert {r["paper_id"] for r in inner_c} < {r["paper_id"] for r in sel_c}


def test_select_nested_excludes_lilaoshi_and_replenishes_from_tail(tmp_path: Path) -> None:
    # 40 candidates; 12 lilaoshi ids sit inside the pool — exclusion happens
    # before the shuffle so the tail replenishes (no mid-run death), and the
    # final intersection is asserted empty.
    src = _write_ids_csv(tmp_path / "ids.csv", _candidate_rows(40))
    rows, _ = build_mod.read_ai2000_rows(src)
    excluded = {f"ai{i:03d}" for i in range(12)}

    sel, inner, stats = build_mod.select_nested(rows, excluded, seed=7, n=10, inner=5)
    sel_ids = {r["paper_id"] for r in sel}
    assert stats["excluded_overlap"] == 12 and stats["candidates"] == 28
    assert sel_ids & excluded == set()
    assert len(sel) == 10 and len(inner) == 5

    # insufficient candidates after exclusion (28 left) -> clear failure
    try:
        build_mod.select_nested(rows, excluded, seed=7, n=30, inner=5)
        raise AssertionError("expected CorpusError for insufficient candidates")
    except build_mod.CorpusError as exc:
        assert "insufficient" in str(exc)


# --------------------------------------------------------------- manifest write


def test_write_single_batch_schema_verbatim_atomic(tmp_path: Path) -> None:
    papers = [
        {"paper_id": "p1", "md_url": "https://x/1.md?sig=abc"},
        {"paper_id": "p2", "md_url": "https://x/2.md"},
    ]
    out_dir = tmp_path / "corpus"
    # stale batch from a previous build must be removed
    stale = out_dir / "job_batch_000.json"
    out_dir.mkdir(parents=True)
    stale.write_text('{"stale": true}\n', encoding="utf-8")

    digest = build_mod.write_single_batch(out_dir, papers)
    out_path = out_dir / "job_batch_000.json"
    assert digest == build_mod.sha256_text(out_path.read_text(encoding="utf-8"))
    # no .tmp residue after the atomic publish
    assert list(out_dir.glob("*.tmp")) == []
    doc = json.loads(out_path.read_text(encoding="utf-8"))
    # p160single schema, machine fields copied verbatim as null
    assert doc["job_batch_id"] == "job_batch_000"
    assert doc["batch_index"] == 0
    assert doc["size"] == 2
    assert doc["machine"] is None and doc["machine_index"] is None and doc["machine_count"] is None
    # entries + order verbatim (URL with query string untouched)
    assert doc["papers"] == papers


def test_derive_md_only_csv_shape(tmp_path: Path) -> None:
    rows = [
        {"paper_id": "a1", "md_url": "https://x/1.md"},
        {"paper_id": "a2", "md_url": "https://x/2.md"},
    ]
    out = tmp_path / "ai2000_has_md_only.csv"
    build_mod.derive_md_only_csv(rows, out)
    with out.open("r", encoding="utf-8", newline="") as f:
        reread = list(csv.reader(f))
    assert reread == [["id", "md_url"], ["a1", "https://x/1.md"], ["a2", "https://x/2.md"]]
    assert list(tmp_path.glob("*.tmp")) == []


# ------------------------------------------------------------------ URL probing


def test_probe_uses_production_resolver_and_reports_failures(
    tmp_path: Path, monkeypatch
) -> None:
    papers = [
        {"paper_id": pid, "md_url": url}
        for pid, _, url in _candidate_rows(20, prefix="pr")
    ]
    calls: list[str] = []

    def fake_ensure_cached(pid: str, url: str, cache_dir: Path | None = None):
        calls.append(pid)
        if pid == "pr000":
            return None, "HTTPError: 404"
        if pid == "pr001":
            # empty-body failure via the production contract: path None + err
            return None, "empty md content"
        target = (cache_dir or tmp_path) / f"{pid}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# md\n", encoding="utf-8")
        return target, None

    monkeypatch.setattr(build_mod, "ensure_cached", fake_ensure_cached)
    results = build_mod.probe_with_production_resolver(papers, count=5, seed=3)

    assert len(results) == 5 and len(calls) == 5
    oks = [r for r in results if r["ok"]]
    fails = [r for r in results if not r["ok"]]
    assert all(r["bytes"] > 0 and r["error"] is None for r in oks)
    # deterministic sample: the fake-failure pids only fail if actually sampled
    sampled = {r["paper_id"] for r in results}
    for r in fails:
        assert r["error"] is not None and r["bytes"] == 0
    assert sampled <= {p["paper_id"] for p in papers}
    # sample is deterministic for a fixed seed
    again = build_mod.probe_with_production_resolver(papers, count=5, seed=3)
    assert [r["paper_id"] for r in again] == [r["paper_id"] for r in results]


# ------------------------------------------------------------- main() e2e (tmp)


def test_main_end_to_end_offline(tmp_path: Path, monkeypatch) -> None:
    # 30 candidates; ai000 overlaps lilaoshi — exclusion removes it from the
    # pool and the tail replenishes (no mid-run death); n=10, inner=5.
    rows = _candidate_rows(30)
    src = _write_ids_csv(tmp_path / "ids.csv", rows)
    lilaoshi_dir = tmp_path / "manifests" / "lilaoshi_aminer_p50"
    lilaoshi_dir.mkdir(parents=True)
    (lilaoshi_dir / "job_batch_000.json").write_text(
        json.dumps({"papers": [{"paper_id": "ai000", "md_url": "https://l/0.md"}]}),
        encoding="utf-8",
    )
    out_n = tmp_path / "manifests" / "ai2000_p500single"
    out_inner = tmp_path / "manifests" / "ai2000_p256single"
    derived = tmp_path / "data" / "ai2000" / "ai2000_has_md_only.csv"

    monkeypatch.setattr(build_mod, "MANIFESTS_ROOT", tmp_path / "manifests")
    monkeypatch.setattr(build_mod, "OUT_DIRS", {5: out_inner, 10: out_n})
    monkeypatch.setattr(build_mod, "DERIVED_CSV", derived)

    rc = build_mod.main(
        [
            "--source", str(src),
            "--seed", "20260821",
            "--n", "10",
            "--inner", "5",
            "--skip-probe",
        ]
    )
    assert rc == 0

    doc_n = json.loads((out_n / "job_batch_000.json").read_text(encoding="utf-8"))
    doc_inner = json.loads((out_inner / "job_batch_000.json").read_text(encoding="utf-8"))
    ids_n = {p["paper_id"] for p in doc_n["papers"]}
    ids_inner = {p["paper_id"] for p in doc_inner["papers"]}
    assert doc_n["size"] == 10 and doc_inner["size"] == 5
    assert ids_inner < ids_n
    assert "ai000" not in ids_n  # lilaoshi overlap removed, tail replenished
    # derived csv carries the FULL has_md==1 subset (30 rows + header)
    with derived.open("r", encoding="utf-8", newline="") as f:
        assert sum(1 for _ in f) == 31
    # no tmp residue anywhere
    assert list((tmp_path / "manifests").rglob("*.tmp")) == []
