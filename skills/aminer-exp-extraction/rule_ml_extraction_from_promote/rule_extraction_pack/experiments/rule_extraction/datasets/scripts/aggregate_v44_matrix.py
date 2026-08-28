"""
Aggregate v4.4 eval matrix results into a single summary JSON.

Reads the per-paper results from each run directory and computes:
- overall fuzzy R/P/F1
- survey (paper 5b1643ba) vs non-survey fuzzy R/P/F1

Output: experiments/rule_extraction/datasets/runs/20260703_gazetteer_20k/
        summary_data.json  (consumed by summary_20k.md)
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
RUNS = PROJECT_ROOT / "experiments" / "rule_extraction" / "datasets" / "runs"
SURVEY_PAPER_ID = "5b1643ba8fbcbf6e5a9bc884"

# run_id -> (label, batch, gazetteer, gold_set)
MATRIX = [
    ("20260703_gaz20k_v41_dev10_manual", "v4.1", "dev_10", "manual", "Gold2"),
    ("20260703_gaz20k_v43_dev10_manual", "v4.3", "dev_10", "manual", "Gold2"),
    ("20260703_gaz20k_v41_dev10_20k", "v4.1", "dev_10", "20k", "Gold2"),
    ("20260703_gaz20k_v44_dev10_20k", "v4.4", "dev_10", "20k", "Gold2"),
    ("20260703_gaz20k_v41_dev20_20k", "v4.1", "dev_20", "20k", "Gold2"),
    ("20260703_gaz20k_v44_dev20_20k", "v4.4", "dev_20", "20k", "Gold2"),
    ("20260703_gaz20k_v41_dev20_20k_gold1", "v4.1", "dev_20", "20k", "Gold1"),
    ("20260703_gaz20k_v44_dev20_20k_gold1", "v4.4", "dev_20", "20k", "Gold1"),
]


def _f1(p: float, r: float) -> float:
    if p + r == 0:
        return 0.0
    return 2 * p * r / (p + r)


def aggregate_run(run_id: str) -> dict[str, Any]:
    run_dir = RUNS / run_id
    results_dir = run_dir / "results"
    if not results_dir.exists():
        return {"run_id": run_id, "error": f"missing {results_dir}"}

    # Load manifest for ground-truth batch/gold_set
    manifest_path = run_dir / "run_manifest.json"
    manifest = {}
    if manifest_path.exists():
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

    # There should be exactly one results file per run.
    result_files = sorted(results_dir.glob("*.json"))
    if not result_files:
        return {"run_id": run_id, "error": "no result files"}

    with open(result_files[0], encoding="utf-8") as f:
        result = json.load(f)

    papers = result.get("papers", [])

    # Per-paper fuzzy metrics; aggregate by micro-averaging matched/missed/extra.
    survey = {"matched": 0, "gold": 0, "pred": 0, "papers": 0}
    non_survey = {"matched": 0, "gold": 0, "pred": 0, "papers": 0}
    per_paper = []

    for p in papers:
        pid = p.get("paper_id", "")
        ev = p.get("evaluation", {}).get("fuzzy", {})
        matched = ev.get("matched_count", 0)
        gold_n = p.get("gold_count", 0)
        pred_n = p.get("rule_count", 0)
        rec = ev.get("recall", 0.0)
        prec = ev.get("precision", 0.0)
        f1 = ev.get("f1", 0.0)
        per_paper.append(
            {
                "paper_id": pid,
                "gold_count": gold_n,
                "rule_count": pred_n,
                "matched": matched,
                "recall": rec,
                "precision": prec,
                "f1": f1,
                "is_survey": pid == SURVEY_PAPER_ID,
            }
        )
        bucket = survey if pid == SURVEY_PAPER_ID else non_survey
        bucket["matched"] += matched
        bucket["gold"] += gold_n
        bucket["pred"] += pred_n
        bucket["papers"] += 1

    def _summarize(b: dict) -> dict[str, Any]:
        r = b["matched"] / b["gold"] if b["gold"] else 0.0
        p = b["matched"] / b["pred"] if b["pred"] else 0.0
        return {
            "papers": b["papers"],
            "gold_total": b["gold"],
            "pred_total": b["pred"],
            "matched_total": b["matched"],
            "recall": r,
            "precision": p,
            "f1": _f1(p, r),
        }

    overall = {
        "papers": survey["papers"] + non_survey["papers"],
        "gold_total": survey["gold"] + non_survey["gold"],
        "pred_total": survey["pred"] + non_survey["pred"],
        "matched_total": survey["matched"] + non_survey["matched"],
    }
    overall["recall"] = overall["matched_total"] / overall["gold_total"] if overall["gold_total"] else 0.0
    overall["precision"] = overall["matched_total"] / overall["pred_total"] if overall["pred_total"] else 0.0
    overall["f1"] = _f1(overall["precision"], overall["recall"])

    return {
        "run_id": run_id,
        "result_file": result_files[0].name,
        "manifest_batch": manifest.get("batch"),
        "manifest_gold_set": manifest.get("gold_set"),
        "manifest_gazetteer_path": manifest.get("gazetteer_path"),
        "overall": overall,
        "survey": _summarize(survey),
        "non_survey": _summarize(non_survey),
        "per_paper": per_paper,
    }


def main() -> None:
    out_dir = RUNS / "20260703_gazetteer_20k"
    out_dir.mkdir(parents=True, exist_ok=True)

    aggregated = []
    for run_id, label, batch, gaz, gold_set in MATRIX:
        entry = aggregate_run(run_id)
        entry["label"] = label
        entry["batch"] = batch
        entry["gazetteer"] = gaz
        entry["gold_set"] = gold_set
        aggregated.append(entry)

    out_path = out_dir / "summary_data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(aggregated, f, indent=2, ensure_ascii=False)

    print(f"Wrote {out_path}")
    print()
    print(f"{'label':<6} {'batch':<7} {'gaz':<7} {'gold':<6} {'R':>7} {'P':>7} {'F1':>7} {'srvF1':>8} {'nonSrvF1':>10}")
    print("-" * 80)
    for e in aggregated:
        o = e.get("overall", {})
        s = e.get("survey", {})
        ns = e.get("non_survey", {})
        if "error" in e:
            print(f"{e['label']:<6} ERROR: {e['error']}")
            continue
        print(
            f"{e['label']:<6} {e['batch']:<7} {e['gazetteer']:<7} {e['gold_set']:<6} "
            f"{o['recall']:>6.2%} {o['precision']:>6.2%} {o['f1']:>6.2%} "
            f"{s['f1']:>7.2%} {ns['f1']:>9.2%}"
        )


if __name__ == "__main__":
    main()
