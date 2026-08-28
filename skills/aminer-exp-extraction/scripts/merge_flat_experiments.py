#!/usr/bin/env python3
"""Default merge: flat experiment-level JSON array from nested job_batch predictions.

For each paper prediction under ``runs/<session_run_id>/job_batch_*/predictions/``,
each experiment becomes one array element. Paper-level fields
(``research_problem``, ``research_problem_description``, ``paper_title``) are
pulled down into every experiment. ``confidence_breakdown`` is dropped;
``confidence`` stays a float. Dedup by ``paper_id`` keeps the highest
``job_batch_NNN`` name.

TODO-V07-11 compacted runs: when ``runs/<session>/compaction/flat_experiments.json``
exists, its rows load FIRST as base rows with the LOWEST precedence — any
on-disk job_batch prediction overrides them (a paper re-run after its window
was compacted wins). Output is written atomically (tmp + os.replace).

Usage (default merge after a bulk run):
    python scripts/merge_flat_experiments.py --session-run-id prod-bulk-20260721ids-v0.2.0

Partial / interrupted run (exclude batches above N):
    python scripts/merge_flat_experiments.py \\
        --session-run-id prod-bulk-20260721ids-v0.2.0 --max-batch 49

Verify an existing export:
    python scripts/merge_flat_experiments.py --verify-only \\
        --out pipeline_output/production/exports/ai2000_prod-bulk-20260721ids-v0.2.0_flat_merged.json

Legacy paper-nested clean merge (not default):
    python scripts/merge_clean_predictions.py --session-run-id ...
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path

PROD_ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = PROD_ROOT / "pipeline_output" / "production" / "runs"
OUT_DIR = PROD_ROOT / "pipeline_output" / "production" / "exports"

_JOB_BATCH_NUM_RE = re.compile(r"^job_batch_(\d+)$")
_JOB_BATCH_ANY_RE = re.compile(r"^job_batch_")

EXPECTED_KEYS = [
    "_id",
    "paper_id",
    "paper_title",
    "experiment_name",
    "research_problem",
    "research_problem_description",
    "research_problem_aliases",
    "research_goal",
    "experiment_subject",
    "methods",
    "datasets",
    "sample_size",
    "metrics",
    "key_results",
    "conclusion",
    "limitations",
    "evidence",
    "domain",
    "experiment_type",
    "experiment_history",
    "score",
]

DATASET_KEYS = [
    "name",
    "aliases",
    "dataset_type",
    "description",
    "sample_size",
    "is_public",
    "is_self_collected",
    "urls",
    "github_urls",
    "doi_list",
    "cstr_list",
    "confidence",
]


def _clean_dataset(ds: dict) -> dict:
    """Keep dataset fields in schema order; drop confidence_breakdown."""
    return {k: ds.get(k) for k in DATASET_KEYS}


def _flatten_experiment(pred: dict, exp: dict) -> dict:
    """Build one flat experiment object with exact key order."""
    datasets = exp.get("datasets") or []
    rp_aliases = pred.get("research_problem_aliases")
    return {
        "_id": exp.get("_id", ""),
        "paper_id": pred.get("paper_id"),
        "paper_title": pred.get("paper_title"),
        "experiment_name": exp.get("experiment_name"),
        "research_problem": pred.get("research_problem", ""),
        "research_problem_description": pred.get("research_problem_description", ""),
        "research_problem_aliases": list(rp_aliases) if isinstance(rp_aliases, list) else [],
        "research_goal": exp.get("research_goal"),
        "experiment_subject": exp.get("experiment_subject"),
        "methods": [
            {
                "name": m.get("name", ""),
                "description": m.get("description", ""),
                "aliases": list(m.get("aliases") or [])
                if isinstance(m.get("aliases"), list)
                else [],
            }
            for m in (exp.get("methods") or [])
            if isinstance(m, dict)
        ],
        "datasets": [_clean_dataset(d) for d in datasets if isinstance(d, dict)],
        "sample_size": exp.get("sample_size"),
        "metrics": exp.get("metrics"),
        "key_results": exp.get("key_results"),
        "conclusion": exp.get("conclusion"),
        "limitations": exp.get("limitations"),
        "evidence": exp.get("evidence"),
        "domain": exp.get("domain"),
        "experiment_type": exp.get("experiment_type"),
        "experiment_history": exp.get("experiment_history", []),
        "score": exp.get("score"),
    }


def _list_job_batch_names(run_dir: Path, max_batch: int | None) -> list[str]:
    """Return sorted job_batch_* names under run_dir, optionally capped.

    Includes numeric ``job_batch_NNN`` and smoke dirs like ``job_batch_smoke``.
    ``max_batch`` only filters numeric batch indices.
    """
    numeric: list[tuple[int, str]] = []
    other: list[str] = []
    if not run_dir.is_dir():
        return []
    for p in run_dir.iterdir():
        if not p.is_dir() or not _JOB_BATCH_ANY_RE.match(p.name):
            continue
        if not (p / "predictions").is_dir():
            continue
        m = _JOB_BATCH_NUM_RE.match(p.name)
        if m:
            nn = int(m.group(1))
            if max_batch is not None and nn > max_batch:
                continue
            numeric.append((nn, p.name))
        else:
            other.append(p.name)
    numeric.sort(key=lambda t: t[0])
    other.sort()
    return [name for _, name in numeric] + other


def _verify(out_path: Path) -> None:
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert isinstance(data, list), "output must be a list"

    for i, obj in enumerate(data):
        keys = list(obj.keys())
        assert keys == EXPECTED_KEYS, (
            f"element {i} keys mismatch:\n  got={keys}\n  expected={EXPECTED_KEYS}"
        )
        assert "method" not in obj, f"element {i}: legacy method key present"
        assert "method_description" not in obj, (
            f"element {i}: legacy method_description key present"
        )
        methods = obj.get("methods")
        assert isinstance(methods, list), f"element {i}: methods must be a list"
        _method_keys = {"name", "description", "aliases"}
        for j, m in enumerate(methods):
            assert isinstance(m, dict), f"element {i} methods[{j}] must be a dict"
            assert set(m.keys()) == _method_keys, (
                f"element {i} methods[{j}] keys={set(m.keys())}, "
                f"expected {{'name', 'description', 'aliases'}}"
            )
        assert obj["research_problem"] is not None, f"element {i}: research_problem is None"
        assert obj["research_problem_description"] is not None, (
            f"element {i}: research_problem_description is None"
        )
        assert isinstance(obj["research_problem_aliases"], list), (
            f"element {i}: research_problem_aliases must be a list"
        )
        for j, ds in enumerate(obj.get("datasets") or []):
            assert "confidence_breakdown" not in ds, (
                f"element {i} dataset {j} still has confidence_breakdown"
            )
            assert "justification" not in ds, (
                f"element {i} dataset {j} still has justification"
            )

    paper_ids = {obj["paper_id"] for obj in data}
    print(f"Verified OK: {len(data)} elements, {len(paper_ids)} unique paper_ids")
    if data:
        print(f"First element keys: {list(data[0].keys())}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--session-run-id",
        type=str,
        action="append",
        default=None,
        help="Merge runs/<session-run-id>/job_batch_*/predictions. Repeatable: later "
        "runs override earlier ones for the same paper_id (e.g. v0.2.0 then v0.4.0).",
    )
    ap.add_argument(
        "--run-dir",
        type=Path,
        action="append",
        default=None,
        help="Explicit session run directory (alternative to --session-run-id). Repeatable.",
    )
    ap.add_argument(
        "--max-batch",
        type=int,
        default=None,
        help="Inclusive max batch index (e.g. 49 => only job_batch_000..049). "
        "Default: all job_batch_* dirs present under the run.",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output JSON path (default: exports/ai2000_<session-run-id>_flat_merged.json)",
    )
    ap.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify an existing output file; do not merge",
    )
    args = ap.parse_args()

    if args.verify_only:
        if args.out is None:
            raise SystemExit("--verify-only requires --out")
        _verify(args.out)
        return

    # Build ordered list of (run_dir, session_label). Later entries override earlier.
    run_specs: list[tuple[Path, str]] = []
    if args.run_dir:
        for rd in args.run_dir:
            run_specs.append((rd, rd.name))
    if args.session_run_id:
        for sid in args.session_run_id:
            run_specs.append((RUNS_DIR / sid, sid))
    if not run_specs:
        raise SystemExit("Provide --session-run-id or --run-dir (repeatable)")

    for run_dir, _label in run_specs:
        if not run_dir.is_dir():
            raise SystemExit(f"Run directory not found: {run_dir}")

    session_label = run_specs[-1][1]  # default output name uses last run
    out_path = args.out or (OUT_DIR / f"ai2000_{session_label}_flat_merged.json")

    print(f"Runs to merge ({len(run_specs)}):")
    for rd, label in run_specs:
        print(f"  - {label}: {rd}")

    # paper_id -> (run_index, batch_name, pred_dict); pred_dict None marks a
    # compacted-base row (flat rows kept separately in flat_base).
    # Later run_index wins; within a run, higher batch_name wins ("job_batch_*"
    # always beats the "compaction" base loaded first).
    winners: dict[str, tuple[int, str, dict | None]] = {}
    flat_base: dict[int, dict[str, list[dict]]] = {}
    total_files = 0
    total_errors = 0
    t0 = time.perf_counter()

    for run_index, (run_dir, _label) in enumerate(run_specs):
        # TODO-V07-11: compacted windows' rows enter as the lowest-precedence
        # base; on-disk tail-batch predictions override them per paper.
        compacted_base = run_dir / "compaction" / "flat_experiments.json"
        if compacted_base.exists():
            try:
                base_rows = json.loads(compacted_base.read_text(encoding="utf-8"))
            except Exception:
                print(f"  (warn: corrupt compaction flat {compacted_base}; ignored)")
                base_rows = []
            base_by_pid: dict[str, list[dict]] = {}
            for r in base_rows:
                pid = r.get("paper_id")
                if pid:
                    base_by_pid.setdefault(pid, []).append(r)
            for pid, rows_ in base_by_pid.items():
                winners[pid] = (run_index, "compaction", None)
                flat_base.setdefault(run_index, {})[pid] = rows_
            if base_by_pid:
                print(f"  compaction base: {len(base_by_pid)} papers "
                      f"({len(base_rows)} rows) from {compacted_base.name}")

        batch_names = _list_job_batch_names(run_dir, args.max_batch)
        if not batch_names:
            print(f"  (skip {run_dir}: no job_batch_*/predictions)")
            continue
        print(f"\nRun {run_index}: {run_dir}")
        print(f"  Batches: {batch_names[0]} .. {batch_names[-1]} ({len(batch_names)} dirs)")
        for i, batch_name in enumerate(batch_names, 1):
            pred_dir = run_dir / batch_name / "predictions"
            run_count = 0
            run_errors = 0
            for pf in sorted(pred_dir.glob("*.json")):
                total_files += 1
                try:
                    pred = json.loads(pf.read_text(encoding="utf-8"))
                except Exception:
                    total_errors += 1
                    run_errors += 1
                    continue

                paper_id = pred.get("paper_id") or pf.stem
                existing = winners.get(paper_id)
                # Later run always wins; within same run, higher batch_name wins.
                if existing is None or run_index > existing[0] or (
                    run_index == existing[0] and batch_name > existing[1]
                ):
                    winners[paper_id] = (run_index, batch_name, pred)
                run_count += 1

            if i % 10 == 0 or i == len(batch_names):
                elapsed = time.perf_counter() - t0
                print(
                    f"  [{i}/{len(batch_names)}] {batch_name}: {run_count} preds"
                    + (f" ({run_errors} errors)" if run_errors else "")
                    + f"  elapsed={elapsed:.1f}s  unique_papers={len(winners)}"
                )

    experiments: list[dict] = []
    for paper_id in sorted(winners):
        _run_index, _batch_name, pred = winners[paper_id]
        if pred is None:  # compacted-base row: already flat
            experiments.extend(flat_base.get(_run_index, {}).get(paper_id, []))
            continue
        exps = pred.get("experiments") or []
        if not exps:
            continue
        for exp in exps:
            if isinstance(exp, dict):
                experiments.append(_flatten_experiment(pred, exp))

    elapsed = time.perf_counter() - t0
    print(f"\nProcessed {total_files} files ({total_errors} errors) in {elapsed:.1f}s")
    print(f"Unique papers: {len(winners)}")
    print(f"Output experiments: {len(experiments)}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Writing {out_path} ...")
    tmp_out = out_path.with_name(out_path.name + ".tmp")
    tmp_out.write_text(
        json.dumps(experiments, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_out, out_path)
    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"Done: {out_path} ({size_mb:.1f} MB)")

    _verify(out_path)


if __name__ == "__main__":
    main()
