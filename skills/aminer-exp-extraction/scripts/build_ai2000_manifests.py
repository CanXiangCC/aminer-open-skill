#!/usr/bin/env python3
"""TODO-V07-10 Part 2: build ai2000 test corpora from data/ai2000_has_md_ids.csv.

Reads the 232,928-row ids CSV (columns id,has_md,md_url), keeps has_md==1
rows with non-empty id/md_url, and deterministically selects two NESTED
single-batch test corpora (fixed seed, reproducible):

  manifests/ai2000_p256single/  job_batch_000.json  (256 papers, PREFIX of 500)
  manifests/ai2000_p500single/  job_batch_000.json  (500 papers)
  manifests/ai2000_p1000single/ job_batch_000.json  (1000 papers, scale probe)

The selection is a seeded deterministic shuffle, so first-N selections are
PREFIXES of each other: rebuilding with --n 1000 --inner 500 rewrites p500
byte-identically (same seed + unchanged candidate pool) and yields the
nesting chain p256 ⊂ p500 ⊂ p1000, which main() asserts across all
on-disk corpora.

Selection contract (single defined behavior, never a mid-run death):
  1. Exclude any paper_id already present in manifests/lilaoshi_aminer_*/
     job_batch_*.json (exclusion BEFORE selection — the candidate tail
     naturally replenishes; no error-and-die on overlap).
  2. Deterministic shuffle with the fixed seed, take the first 500, then the
     first 256 as the nested subset; assert p256 ⊂ p500, both duplicate-free,
     and final intersection with lilaoshi == 0.

Also derives data/ai2000/ai2000_has_md_only.csv (columns id,md_url — the full
has_md==1 subset) which repairs the --smoke CSV path referenced by
scripts/run_bulk.py:725 but missing locally.

Verification (all must pass, phase7_resplit_manifests.py conventions):
  - manifest schema mirrors lilaoshi_aminer_p160single/job_batch_000.json:
    job_batch_id/batch_index/size/machine/machine_index/machine_count/papers
  - written files re-read and compared VERBATIM (entries + order) against the
    selected sequence; sha256 of every written file printed for the report.
  - optional URL reachability probe: N sampled md_urls fetched through the
    PRODUCTION resolver (pipeline/evaluation/md_resolver.ensure_cached) into a
    throwaway temp cache — same requests/redirect/status/non-empty-body
    semantics as real runs; any probe failure fails the command (non-zero).

Outputs live under gitignored paths only (manifests/**, data/ai2000/); only
this script and its tests are committed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import sys
import tempfile
from pathlib import Path

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))

from pipeline.evaluation.md_resolver import ensure_cached  # noqa: E402

DEFAULT_SOURCE = PROD_ROOT / "data" / "ai2000_has_md_ids.csv"
MANIFESTS_ROOT = PROD_ROOT / "manifests"
LILAOSHI_GLOB = "lilaoshi_aminer_*"
OUT_DIRS = {
    256: MANIFESTS_ROOT / "ai2000_p256single",
    500: MANIFESTS_ROOT / "ai2000_p500single",
    1000: MANIFESTS_ROOT / "ai2000_p1000single",
}
DERIVED_CSV = PROD_ROOT / "data" / "ai2000" / "ai2000_has_md_only.csv"
REQUIRED_COLUMNS = ("id", "has_md", "md_url")


class CorpusError(Exception):
    """Fatal input/contract violation (bad CSV, too few candidates, ...)."""


def _rel(path: Path) -> Path:
    """Repo-relative display path; falls back to the absolute path for
    out-of-tree targets (tests, custom --source runs)."""
    try:
        return path.relative_to(PROD_ROOT)
    except ValueError:
        return path


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_ai2000_rows(path: Path) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Filter the ids CSV to the has_md==1 / non-empty candidate pool.

    Returns (rows, stats); rows are {"paper_id": id, "md_url": url} with the
    source strings passed through verbatim (URLs never rewritten). Duplicate
    candidate ids are a source-integrity error (manifest paper_id uniqueness
    would be violated).
    """
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        missing = [c for c in REQUIRED_COLUMNS if c not in header]
        if missing:
            raise CorpusError(f"{path.name}: missing columns {missing} (header={header})")
        rows: list[dict[str, str]] = []
        seen: set[str] = set()
        stats = {"total": 0, "has_md": 0, "dropped_no_url": 0, "kept": 0, "duplicates": 0}
        for raw in reader:
            stats["total"] += 1
            pid = (raw.get("id") or "").strip()
            url = (raw.get("md_url") or "").strip()
            flag = (raw.get("has_md") or "").strip()
            if flag != "1":
                continue
            stats["has_md"] += 1
            if not url or not pid:
                stats["dropped_no_url"] += 1
                continue
            if pid in seen:
                stats["duplicates"] += 1
                raise CorpusError(f"{path.name}: duplicate candidate id {pid!r}")
            seen.add(pid)
            rows.append({"paper_id": pid, "md_url": url})
        stats["kept"] = len(rows)
    return rows, stats


def read_lilaoshi_ids(manifest_root: Path) -> set[str]:
    """All paper_ids in existing manifests/lilaoshi_aminer_*/job_batch_*.json."""
    ids: set[str] = set()
    for batch_file in sorted(manifest_root.glob(f"{LILAOSHI_GLOB}/job_batch_*.json")):
        doc = json.loads(batch_file.read_text(encoding="utf-8"))
        for paper in doc.get("papers") or []:
            pid = paper.get("paper_id")
            if pid:
                ids.add(str(pid))
    return ids


def select_nested(
    rows: list[dict[str, str]],
    excluded_ids: set[str],
    *,
    seed: int,
    n: int = 500,
    inner: int = 256,
) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, int]]:
    """Deterministic nested selection: first-n of the shuffled candidate pool,
    first-inner of that (inner ⊂ n). Lilaoshi exclusion happens BEFORE the
    shuffle, so removals are replenished from the candidate tail naturally.
    """
    if not 0 < inner <= n:
        raise CorpusError(f"require 0 < inner ({inner}) <= n ({n})")
    candidates = [r for r in rows if r["paper_id"] not in excluded_ids]
    if len(candidates) < n:
        raise CorpusError(
            f"candidates insufficient: {len(candidates)} < {n} "
            f"(source kept={len(rows)}, excluded={len(rows) - len(candidates)})"
        )
    rng = random.Random(seed)
    rng.shuffle(candidates)
    selected_n = candidates[:n]
    selected_inner = selected_n[:inner]
    ids_n = [r["paper_id"] for r in selected_n]
    ids_inner = {r["paper_id"] for r in selected_inner}
    if len(ids_n) != n or len(set(ids_n)) != n:
        raise CorpusError("selection produced duplicate paper_ids (impossible after read filter)")
    if not ids_inner < set(ids_n):
        raise CorpusError("inner selection is not a strict subset of the n selection")
    if ids_inner & excluded_ids or set(ids_n) & excluded_ids:
        raise CorpusError("selection overlaps the lilaoshi corpus after exclusion")
    stats = {
        "source_kept": len(rows),
        "excluded_overlap": len(rows) - len(candidates),
        "candidates": len(candidates),
        "selected": n,
        "selected_inner": inner,
        "seed": seed,
    }
    return selected_n, selected_inner, stats


def write_single_batch(out_dir: Path, papers: list[dict[str, str]]) -> str:
    """Write one job_batch manifest (p160single schema) atomically + verify.

    tmp -> readback verbatim check -> os.replace; returns the file sha256.
    """
    doc = {
        "job_batch_id": "job_batch_000",
        "batch_index": 0,
        "size": len(papers),
        "machine": None,
        "machine_index": None,
        "machine_count": None,
        "papers": [{"paper_id": p["paper_id"], "md_url": p["md_url"]} for p in papers],
    }
    text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("job_batch_*.json"):
        print(f"  removing stale {_rel(stale)}")
        stale.unlink()
    out_path = out_dir / "job_batch_000.json"
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    # readback verbatim accounting BEFORE the atomic publish
    reread = json.loads(tmp_path.read_text(encoding="utf-8"))
    if reread != doc:
        raise CorpusError(f"{out_path.name}: readback differs from intended doc")
    if [p["paper_id"] for p in reread["papers"]] != [p["paper_id"] for p in papers]:
        raise CorpusError(f"{out_path.name}: paper order changed on write")
    os.replace(tmp_path, out_path)
    digest = sha256_text(text)
    print(
        f"  wrote {_rel(out_path)} ({len(papers)} papers, "
        f"sha256={digest})"
    )
    return digest


def derive_md_only_csv(rows: list[dict[str, str]], output: Path) -> str:
    """Write the full has_md==1 subset as id,md_url (repairs --smoke path)."""
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output.with_suffix(output.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "md_url"])
        for r in rows:
            writer.writerow([r["paper_id"], r["md_url"]])
    # readback accounting
    with tmp_path.open("r", encoding="utf-8", newline="") as f:
        reread = list(csv.reader(f))
    if len(reread) != len(rows) + 1 or reread[0] != ["id", "md_url"]:
        raise CorpusError("derived md-only csv readback mismatch")
    os.replace(tmp_path, output)
    digest = sha256_text(output.read_text(encoding="utf-8"))
    print(f"  wrote {_rel(output)} ({len(rows)} rows, sha256={digest})")
    return digest


def probe_with_production_resolver(
    papers: list[dict[str, str]],
    *,
    count: int,
    seed: int,
) -> list[dict[str, object]]:
    """Sample `count` md_urls and fetch them through the PRODUCTION resolver
    (ensure_cached) into a throwaway temp cache — same requests/redirect/
    status/non-empty-body semantics as a real run. Never touches the formal
    MD cache. Any failure is reported per-URL (non-empty error string).
    """
    rng = random.Random(seed)
    sample_idx = sorted(rng.sample(range(len(papers)), min(count, len(papers))))
    results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="ai2000_probe_") as td:
        cache = Path(td)
        for idx in sample_idx:
            paper = papers[idx]
            path, err = ensure_cached(paper["paper_id"], paper["md_url"], cache)
            ok = path is not None and Path(path).exists() and Path(path).stat().st_size > 0
            results.append(
                {
                    "paper_id": paper["paper_id"],
                    "md_url": paper["md_url"],
                    "ok": bool(ok),
                    "bytes": Path(path).stat().st_size if path is not None and Path(path).exists() else 0,
                    "error": err,
                }
            )
            status = "OK" if ok else f"FAIL ({err})"
            print(f"  probe[{idx}] {paper['paper_id']}: {status}")
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--seed", type=int, default=20260821)
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--inner", type=int, default=256)
    ap.add_argument("--probe-count", type=int, default=20)
    ap.add_argument("--skip-probe", action="store_true", help="offline build (tests only)")
    args = ap.parse_args(argv)

    if not args.source.is_file():
        print(f"ERROR: source CSV not found: {args.source}", file=sys.stderr)
        return 1

    print(f"source: {args.source}")
    print(f"source sha256: {sha256_text(args.source.read_text(encoding='utf-8'))}")
    try:
        rows, read_stats = read_ai2000_rows(args.source)
        print(f"candidates: {read_stats}")
        excluded = read_lilaoshi_ids(MANIFESTS_ROOT)
        print(f"lilaoshi paper_ids loaded: {len(excluded)}")
        selected_n, selected_inner, sel_stats = select_nested(
            rows, excluded, seed=args.seed, n=args.n, inner=args.inner
        )
        print(f"selection: {sel_stats}")
        remaining = set(ids for ids in excluded)
        final_intersection = remaining & {r["paper_id"] for r in selected_n}
        if final_intersection:
            print(f"ERROR: lilaoshi intersection not empty: {sorted(final_intersection)}",
                  file=sys.stderr)
            return 1

        print("writing manifests:")
        digests = {
            f"p{args.n}": write_single_batch(OUT_DIRS[args.n], selected_n),
            f"p{args.inner}": write_single_batch(OUT_DIRS[args.inner], selected_inner),
        }
        # cross-check the two written corpora from disk: nested + unique
        on_disk_n = {p["paper_id"] for p in json.loads(
            (OUT_DIRS[args.n] / "job_batch_000.json").read_text(encoding="utf-8"))["papers"]}
        on_disk_inner = {p["paper_id"] for p in json.loads(
            (OUT_DIRS[args.inner] / "job_batch_000.json").read_text(encoding="utf-8"))["papers"]}
        if not on_disk_inner < on_disk_n:
            print(f"ERROR: on-disk corpora are not nested (p{args.inner} ⊄ p{args.n})",
                  file=sys.stderr)
            return 1
        # nesting chain: every smaller registered corpus already on disk must
        # also be a strict subset of the freshly written n-corpus (same seed
        # => first-N selections are prefixes of each other).
        for smaller, d in sorted(OUT_DIRS.items()):
            if smaller >= args.n or smaller == args.inner:
                continue
            f = d / "job_batch_000.json"
            if not f.is_file():
                continue
            ids_smaller = {p["paper_id"] for p in json.loads(
                f.read_text(encoding="utf-8"))["papers"]}
            if not ids_smaller < on_disk_n:
                print(f"ERROR: on-disk p{smaller} is not a strict subset of p{args.n}",
                      file=sys.stderr)
                return 1

        print("deriving md-only csv:")
        digests["md_only_csv"] = derive_md_only_csv(rows, DERIVED_CSV)

        probe_results: list[dict[str, object]] = []
        if not args.skip_probe:
            print(f"probing {args.probe_count} md_urls through the production resolver:")
            probe_results = probe_with_production_resolver(
                selected_n, count=args.probe_count, seed=args.seed
            )
            failed = [r for r in probe_results if not r["ok"]]
            print(f"probe summary: ok={len(probe_results) - len(failed)} "
                  f"fail={len(failed)}/{len(probe_results)}")

        print(f"OK: sha256 {digests}")
        if any(not r["ok"] for r in probe_results):
            print("ERROR: probe failures — see per-URL lines above", file=sys.stderr)
            return 1
    except CorpusError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
