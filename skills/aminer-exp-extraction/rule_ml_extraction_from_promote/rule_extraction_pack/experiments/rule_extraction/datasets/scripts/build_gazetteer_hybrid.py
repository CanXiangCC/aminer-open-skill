"""
Build gazetteer_hybrid.json for v4.5 extract.

  gazetteer_hybrid =
    ALL entries from gazetteer.json (manual core, highest priority)
    ∪ { e ∈ gazetteer_20k.json | e.paper_count >= min_paper_count }

Dedup key: normalize_name (same as build_gazetteer.py / build_gazetteer_20k.py).
On conflict: keep manual canonical_name + aliases.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.datasets.scripts.build_gazetteer import normalize_name  # noqa: E402

DATA_DIR = project_root / "experiments" / "rule_extraction" / "datasets" / "data"


def _entry_norm_keys(entry: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for raw in [entry.get("canonical_name", "")] + list(entry.get("aliases") or []):
        nk = normalize_name(str(raw))
        if nk:
            keys.add(nk)
    for nk in entry.get("normalized_keys") or []:
        if nk:
            keys.add(normalize_name(str(nk)))
    canon = entry.get("canonical_name", "")
    if canon:
        keys.add(normalize_name(canon))
    return keys


def _primary_key(entry: dict[str, Any]) -> str:
    keys = _entry_norm_keys(entry)
    if not keys:
        return ""
    canon = normalize_name(str(entry.get("canonical_name") or ""))
    return canon if canon in keys else min(keys)


def build_hybrid(
    manual_path: Path,
    auto_path: Path,
    min_paper_count: int = 10,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with open(manual_path, encoding="utf-8") as f:
        manual_entries: list[dict[str, Any]] = json.load(f)
    with open(auto_path, encoding="utf-8") as f:
        auto_entries: list[dict[str, Any]] = json.load(f)

    by_key: dict[str, dict[str, Any]] = {}
    manual_keys: set[str] = set()
    auto_eligible = 0
    only_20k_keys: set[str] = set()
    overlap_keys: set[str] = set()

    for entry in manual_entries:
        pk = _primary_key(entry)
        if not pk:
            continue
        out = {
            "canonical_name": entry.get("canonical_name", ""),
            "aliases": list(entry.get("aliases") or []),
            "paper_count": entry.get("paper_count", 0),
            "normalized_keys": sorted(_entry_norm_keys(entry)),
        }
        by_key[pk] = out
        manual_keys.add(pk)

    auto_keys_seen: set[str] = set()
    for entry in auto_entries:
        pc = int(entry.get("paper_count") or 0)
        if pc < min_paper_count:
            continue
        auto_eligible += 1
        pk = _primary_key(entry)
        if not pk:
            continue
        auto_keys_seen.add(pk)
        if pk in by_key:
            overlap_keys.add(pk)
            continue
        by_key[pk] = {
            "canonical_name": entry.get("canonical_name", ""),
            "aliases": list(entry.get("aliases") or []),
            "paper_count": pc,
            "normalized_keys": sorted(_entry_norm_keys(entry)),
        }
        only_20k_keys.add(pk)

    only_manual = manual_keys - auto_keys_seen
    merged = sorted(by_key.values(), key=lambda e: (-int(e.get("paper_count") or 0), e["canonical_name"].lower()))

    stats = {
        "manual_path": str(manual_path),
        "auto_path": str(auto_path),
        "min_paper_count": min_paper_count,
        "manual_count": len(manual_entries),
        "auto_total": len(auto_entries),
        "auto_eligible_count": auto_eligible,
        "merged_total": len(merged),
        "only_manual": len(only_manual),
        "only_20k": len(only_20k_keys),
        "overlap": len(overlap_keys),
    }
    return merged, stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Build hybrid gazetteer for v4.5")
    parser.add_argument("--manual", type=Path, default=DATA_DIR / "gazetteer.json")
    parser.add_argument("--auto", type=Path, default=DATA_DIR / "gazetteer_20k.json")
    parser.add_argument("--min-paper-count", type=int, default=10)
    parser.add_argument("--output", type=Path, default=DATA_DIR / "gazetteer_hybrid.json")
    parser.add_argument("--stats-output", type=Path, default=DATA_DIR / "gazetteer_hybrid_stats.json")
    args = parser.parse_args()

    if not args.manual.exists():
        raise SystemExit(f"Manual gazetteer not found: {args.manual}")
    if not args.auto.exists():
        raise SystemExit(f"Auto gazetteer not found: {args.auto}. Run build_gazetteer_20k.py first.")

    merged, stats = build_hybrid(args.manual, args.auto, args.min_paper_count)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    stats["output"] = str(args.output)
    with open(args.stats_output, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print(json.dumps(stats, indent=2, ensure_ascii=False))
    print(f"Saved hybrid gazetteer ({len(merged)} entries) to {args.output}")


if __name__ == "__main__":
    main()
