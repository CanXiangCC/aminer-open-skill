"""
Build gazetteer_v4_4 (gazetteer_20k.json) from 20K per-paper LLM extractions.

Input:  bulk_extraction_section_union_glm45_airx/outputs/per_paper/*.json
        (read-only; each file is a list of experiment objects with `datasets`)
Output: experiments/rule_extraction/datasets/data/gazetteer_20k.json

Dedup: group by normalize_name; paper_count = #distinct paper_ids;
       canonical_name = longest original form.
min_paper_count = 2 (matches original build_gazetteer.py).
"""

import json
import re
import sys
from pathlib import Path
from collections import defaultdict
from typing import Any, Dict, List, Set

# project_root = scripts/datasets/rule_extraction/experiments/ -> root
project_root = Path(__file__).resolve().parent.parent.parent.parent.parent

# Reuse the original builder's normalization + model blacklist so the new
# gazetteer stays compatible with v3_gazetteer matching semantics.
sys.path.insert(0, str(project_root))
from experiments.rule_extraction.datasets.scripts.build_gazetteer import (  # noqa: E402
    normalize_name,
    is_model_name,
)


def build_gazetteer_20k(
    per_paper_dir: Path,
    output_path: Path,
    min_paper_count: int = 2,
) -> List[Dict[str, Any]]:
    per_paper_files = sorted(per_paper_dir.glob("*.json"))
    total_files = len(per_paper_files)
    print(f"Scanning {total_files} per-paper files in {per_paper_dir}")

    # normalized_name -> {paper_ids}
    name_papers: Dict[str, Set[str]] = defaultdict(set)
    # normalized_name -> [original_name_forms] (across names + aliases)
    name_forms: Dict[str, List[str]] = defaultdict(list)
    # normalized_name -> {normalized_alias_keys} (for normalized_keys set)
    name_norm_keys: Dict[str, Set[str]] = defaultdict(set)

    valid_files = 0
    skipped_non_list = 0
    skipped_empty = 0
    skipped_no_paper_id = 0
    total_experiments = 0
    total_dataset_records = 0
    per_file_paper_ids: Set[str] = set()

    for i, fp in enumerate(per_paper_files, 1):
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            skipped_non_list += 1
            continue

        if not isinstance(data, list):
            skipped_non_list += 1
            continue
        if not data:
            skipped_empty += 1
            continue

        # paper_id: prefer the experiment object's paper_id; fall back to filename.
        file_paper_id = fp.stem
        file_paper_id_seen = False
        valid_files += 1
        total_experiments += len(data)

        for exp in data:
            if not isinstance(exp, dict):
                continue
            paper_id = exp.get("paper_id") or file_paper_id
            if not paper_id:
                skipped_no_paper_id += 1
                continue
            if paper_id == file_paper_id:
                file_paper_id_seen = True

            datasets = exp.get("datasets") or []
            for ds in datasets:
                if not isinstance(ds, dict):
                    continue
                total_dataset_records += 1
                name = (ds.get("name") or "").strip()
                if not name or is_model_name(name):
                    continue
                norm = normalize_name(name)
                if not norm:
                    continue
                name_papers[norm].add(paper_id)
                name_forms[norm].append(name)
                name_norm_keys[norm].add(norm)

                for alias in ds.get("aliases") or []:
                    if not alias or not str(alias).strip():
                        continue
                    alias_str = str(alias).strip()
                    alias_norm = normalize_name(alias_str)
                    if not alias_norm:
                        continue
                    # Map alias back to the same canonical group so the alias
                    # contributes to paper_count and normalized_keys.
                    name_papers[norm].add(paper_id)
                    name_forms[norm].append(alias_str)
                    name_norm_keys[norm].add(alias_norm)
                    # Also index the alias directly so it can match on its own.
                    name_papers[alias_norm].add(paper_id)
                    name_forms[alias_norm].append(alias_str)
                    name_norm_keys[alias_norm].add(alias_norm)

        if file_paper_id_seen:
            per_file_paper_ids.add(file_paper_id)

    print(f"  valid files: {valid_files}")
    print(f"  skipped (non-list/parse error): {skipped_non_list}")
    print(f"  skipped (empty list): {skipped_empty}")
    print(f"  total experiments: {total_experiments}")
    print(f"  total dataset records: {total_dataset_records}")
    print(f"  distinct paper_ids seen: {len(per_file_paper_ids)}")

    # Build gazetteer entries.
    gazetteer: List[Dict[str, Any]] = []
    for norm, paper_ids in name_papers.items():
        if len(paper_ids) < min_paper_count:
            continue
        forms = name_forms.get(norm, [])
        if not forms:
            continue
        canonical_name = max(set(forms), key=len)
        aliases = sorted(set(forms) - {canonical_name})
        normalized_keys = sorted(name_norm_keys.get(norm, {norm}))
        gazetteer.append(
            {
                "canonical_name": canonical_name,
                "aliases": aliases,
                "normalized_keys": normalized_keys,
                "paper_count": len(paper_ids),
            }
        )

    # Sort by paper_count desc, then canonical_name asc for stable order.
    gazetteer.sort(key=lambda e: (-e["paper_count"], e["canonical_name"].lower()))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(gazetteer, f, indent=2, ensure_ascii=False)
    print(f"Saved gazetteer to: {output_path}")

    return gazetteer


def compare_with_original(gazetteer_20k: List[Dict[str, Any]]) -> Dict[str, Any]:
    orig_path = (
        project_root
        / "experiments"
        / "rule_extraction"
        / "datasets"
        / "data"
        / "gazetteer.json"
    )
    if not orig_path.exists():
        return {"compared": False, "reason": f"{orig_path} not found"}
    with open(orig_path, "r", encoding="utf-8") as f:
        orig = json.load(f)
    orig_norm = {n for e in orig for n in e.get("normalized_keys", [])}
    new_norm = {n for e in gazetteer_20k for n in e.get("normalized_keys", [])}
    only_new = new_norm - orig_norm
    only_orig = orig_norm - new_norm
    overlap = orig_norm & new_norm
    return {
        "compared": True,
        "orig_entries": len(orig),
        "new_entries": len(gazetteer_20k),
        "orig_normalized_keys": len(orig_norm),
        "new_normalized_keys": len(new_norm),
        "overlap_keys": len(overlap),
        "only_in_new": len(only_new),
        "only_in_orig": len(only_orig),
    }


def main() -> None:
    per_paper_dir = (
        project_root
        / "bulk_extraction_section_union_glm45_airx"
        / "outputs"
        / "per_paper"
    )
    output_path = (
        project_root
        / "experiments"
        / "rule_extraction"
        / "datasets"
        / "data"
        / "gazetteer_20k.json"
    )

    if not per_paper_dir.exists():
        print(f"Error: per_paper dir not found: {per_paper_dir}")
        return

    gazetteer = build_gazetteer_20k(per_paper_dir, output_path, min_paper_count=2)

    print("\n=== gazetteer_20k Statistics ===")
    print(f"Total entries: {len(gazetteer)}")
    if gazetteer:
        top = gazetteer[:15]
        print("\nTop 15 datasets by paper_count:")
        for e in top:
            print(f"  - {e['canonical_name']}: {e['paper_count']} papers")

        # paper_count distribution
        from collections import Counter
        dist = Counter(e["paper_count"] for e in gazetteer)
        print("\npaper_count distribution (top buckets):")
        for pc in sorted(dist.keys())[:10]:
            print(f"  paper_count={pc}: {dist[pc]} entries")
        big = sum(1 for e in gazetteer if e["paper_count"] >= 10)
        mid = sum(1 for e in gazetteer if 5 <= e["paper_count"] < 10)
        small = sum(1 for e in gazetteer if 2 <= e["paper_count"] < 5)
        print(f"\n  entries with paper_count>=10: {big}")
        print(f"  entries with 5<=paper_count<10: {mid}")
        print(f"  entries with 2<=paper_count<5: {small}")

    cmp = compare_with_original(gazetteer)
    print("\n=== Compare with original gazetteer.json ===")
    if cmp.get("compared"):
        print(f"  orig entries:        {cmp['orig_entries']}")
        print(f"  new entries:         {cmp['new_entries']}")
        print(f"  orig norm_keys:      {cmp['orig_normalized_keys']}")
        print(f"  new norm_keys:       {cmp['new_normalized_keys']}")
        print(f"  overlap:             {cmp['overlap_keys']}")
        print(f"  only in new (added): {cmp['only_in_new']}")
        print(f"  only in orig (lost): {cmp['only_in_orig']}")
    else:
        print(f"  {cmp.get('reason')}")

    # Write a stats summary JSON alongside the gazetteer.
    stats_path = output_path.parent / "gazetteer_20k_stats.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "total_entries": len(gazetteer),
                "top_15": [
                    {"canonical_name": e["canonical_name"], "paper_count": e["paper_count"]}
                    for e in gazetteer[:15]
                ],
                "comparison": cmp,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"\nStats written to: {stats_path}")


if __name__ == "__main__":
    main()
