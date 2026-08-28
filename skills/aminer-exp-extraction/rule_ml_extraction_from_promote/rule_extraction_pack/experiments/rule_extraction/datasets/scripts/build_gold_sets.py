"""
Build Gold1 (per_experiment) and Gold2 (paper_union) for datasets rule extraction.

Source: data/gold/{batch}/full_text_glm5_2/
Output: experiments/rule_extraction/datasets/data/gold/{batch}/
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


def normalize_name(name: str) -> str:
    if not name:
        return ""
    n = name.lower().strip()
    n = re.sub(r"[\s\-_]+", "", n)
    return n


def _richer(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Keep the entry with more complete description / sample_size."""
    score_a = len(a.get("description") or "") + (1 if a.get("sample_size") else 0)
    score_b = len(b.get("description") or "") + (1 if b.get("sample_size") else 0)
    winner = a if score_a >= score_b else b
    loser = b if winner is a else a
    merged = dict(winner)
    aliases = set(merged.get("aliases") or [])
    aliases.update(loser.get("aliases") or [])
    if loser.get("name") and loser["name"] != merged.get("name"):
        aliases.add(loser["name"])
    merged["aliases"] = sorted(aliases)
    return merged


def merge_paper_datasets(experiments: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Union datasets across experiments with dedup by normalized name."""
    by_norm: dict[str, dict[str, Any]] = {}
    merged_from: list[dict[str, str]] = []
    exp_names: list[str] = []

    for exp in experiments:
        exp_name = exp.get("experiment_name") or ""
        if exp_name:
            exp_names.append(exp_name)
        for ds in exp.get("datasets") or []:
            name = ds.get("name")
            if not name:
                continue
            key = normalize_name(name)
            if not key:
                continue
            if key in by_norm:
                by_norm[key] = _richer(by_norm[key], ds)
                merged_from.append({"normalized": key, "action": "merged_duplicate"})
            else:
                by_norm[key] = dict(ds)
                merged_from.append({"normalized": key, "action": "added", "from_experiment": exp_name})

    meta = {
        "source_experiment_count": len(experiments),
        "source_experiment_names": exp_names,
        "merged_from": merged_from,
        "dataset_count": len(by_norm),
    }
    return sorted(by_norm.values(), key=lambda d: (d.get("name") or "").lower()), meta


def build_gold_sets(batch: str, project_root: Path) -> dict[str, Any]:
    src_dir = project_root / "data" / "gold" / batch / "full_text_glm5_2"
    out_base = project_root / "experiments" / "rule_extraction" / "datasets" / "data" / "gold" / batch
    per_exp_dir = out_base / "per_experiment"
    union_dir = out_base / "paper_union"
    per_exp_dir.mkdir(parents=True, exist_ok=True)
    union_dir.mkdir(parents=True, exist_ok=True)

    stats: dict[str, Any] = {
        "batch": batch,
        "built_at": datetime.now().isoformat(),
        "source_dir": str(src_dir),
        "papers": [],
        "total_papers": 0,
        "total_datasets_per_experiment_first": 0,
        "total_datasets_paper_union": 0,
        "multi_experiment_papers": [],
    }

    for json_file in sorted(src_dir.glob("*.json")):
        if json_file.parent.name == "traces":
            continue
        paper_id = json_file.stem
        with open(json_file, encoding="utf-8") as f:
            data = json.load(f)
        experiments = data if isinstance(data, list) else [data]

        # Gold1: copy experiment array as-is
        per_exp_path = per_exp_dir / f"{paper_id}.json"
        with open(per_exp_path, "w", encoding="utf-8") as f:
            json.dump(experiments, f, indent=2, ensure_ascii=False)

        # Gold2: paper union
        union_datasets, merge_meta = merge_paper_datasets(experiments)
        union_doc = {
            "paper_id": paper_id,
            "datasets": union_datasets,
            **merge_meta,
        }
        union_path = union_dir / f"{paper_id}.json"
        with open(union_path, "w", encoding="utf-8") as f:
            json.dump(union_doc, f, indent=2, ensure_ascii=False)

        # First-experiment-only count (legacy loader behavior)
        first_count = 0
        for exp in experiments:
            ds = exp.get("datasets") or []
            if ds:
                first_count = len(ds)
                break

        per_exp_ds_total = sum(len(exp.get("datasets") or []) for exp in experiments)
        paper_stat = {
            "paper_id": paper_id,
            "experiment_count": len(experiments),
            "datasets_first_experiment": first_count,
            "datasets_all_experiments_raw": per_exp_ds_total,
            "datasets_paper_union": len(union_datasets),
            "union_dataset_names": [d.get("name") for d in union_datasets],
        }
        stats["papers"].append(paper_stat)
        stats["total_papers"] += 1
        stats["total_datasets_per_experiment_first"] += first_count
        stats["total_datasets_paper_union"] += len(union_datasets)
        if len(experiments) > 1:
            stats["multi_experiment_papers"].append(paper_id)

    stats_path = out_base / "build_stats.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Build datasets gold sets")
    parser.add_argument("--batch", default="dev_10")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    stats = build_gold_sets(args.batch, project_root)
    print(f"Built gold for {stats['total_papers']} papers")
    print(f"  paper_union total datasets: {stats['total_datasets_paper_union']}")
    print(f"  legacy first-experiment total: {stats['total_datasets_per_experiment_first']}")
    if stats["multi_experiment_papers"]:
        print(f"  multi-experiment papers: {stats['multi_experiment_papers']}")


if __name__ == "__main__":
    main()
