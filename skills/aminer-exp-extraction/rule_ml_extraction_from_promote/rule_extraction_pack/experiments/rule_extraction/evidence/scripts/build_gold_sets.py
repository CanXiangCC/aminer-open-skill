"""
Build Gold1 (per_experiment) for evidence rule extraction.

Source: data/gold/{batch}/full_text_glm5_2/
Output: experiments/rule_extraction/evidence/data/gold/{batch}/per_experiment/
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.evaluation.semantic import normalize_text

EVIDENCE_ROOT = Path(__file__).resolve().parent.parent

# dev_20 multi-experiment papers (consistent with datasets experiment)
MULTI_EXPERIMENT_PAPER_IDS_DEV_20 = [
    "628304515aee126c0f6f0e05",
    "659e2146939a5f4082894306",
    "661ddba813fb2c6cf6b5d7e6",
    "6632f3d201d2a3fbfc5b36bb",
    "66bac1ca01d2a3fbfcd435ac",
]

STRIP_FIELDS = {"datasets", "evidence"}


def is_verbatim_in_md(sentence: str, md_text: str) -> bool:
    """Check if sentence (normalized) is a substring of md (normalized)."""
    if not sentence or not md_text:
        return False
    norm_s = normalize_text(sentence)
    norm_md = normalize_text(md_text)
    if norm_s and norm_s in norm_md:
        return True
    return sentence.strip() in md_text


def load_gold_experiments_stripped(paper_id: str, batch: str = "dev_10") -> list[dict[str, Any]]:
    """Load gold experiments with datasets and evidence removed."""
    gold_path = EVIDENCE_ROOT / "data" / "gold" / batch / "per_experiment" / f"{paper_id}.json"
    with open(gold_path, encoding="utf-8") as f:
        experiments = json.load(f)
    if not isinstance(experiments, list):
        experiments = [experiments]
    stripped = []
    for exp in experiments:
        copy = {k: v for k, v in exp.items() if k not in STRIP_FIELDS}
        stripped.append(copy)
    return stripped


def _load_md_for_paper(paper_id: str, batch: str, project_root: Path) -> str | None:
    manifest_path = project_root / "data" / "fixtures" / batch / "manifest.json"
    if not manifest_path.exists():
        return None
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    for item in manifest:
        if item.get("paper_id") == paper_id:
            md_path = item.get("md_path")
            if md_path:
                full = project_root / md_path
                if full.exists():
                    return full.read_text(encoding="utf-8")
    return None


def build_gold_sets(batch: str, project_root: Path) -> dict[str, Any]:
    t0 = time.perf_counter()
    src_dir = project_root / "data" / "gold" / batch / "full_text_glm5_2"
    out_base = EVIDENCE_ROOT / "data" / "gold" / batch
    per_exp_dir = out_base / "per_experiment"
    per_exp_dir.mkdir(parents=True, exist_ok=True)

    evidence_counts: list[int] = []
    substring_hits = 0
    substring_total = 0

    stats: dict[str, Any] = {
        "batch": batch,
        "built_at": datetime.now().isoformat(),
        "source_dir": str(src_dir),
        "papers": 0,
        "experiments": 0,
        "evidence_sentences_total": 0,
        "multi_experiment_paper_ids": [],
    }

    for json_file in sorted(src_dir.glob("*.json")):
        if json_file.parent.name == "traces":
            continue
        paper_id = json_file.stem
        with open(json_file, encoding="utf-8") as f:
            data = json.load(f)
        experiments = data if isinstance(data, list) else [data]

        per_exp_path = per_exp_dir / f"{paper_id}.json"
        with open(per_exp_path, "w", encoding="utf-8") as f:
            json.dump(experiments, f, indent=2, ensure_ascii=False)

        md_text = _load_md_for_paper(paper_id, batch, project_root)
        exp_count = len(experiments)
        paper_evidence = 0
        paper_substring_hits = 0

        for exp in experiments:
            ev_list = exp.get("evidence") or []
            paper_evidence += len(ev_list)
            evidence_counts.append(len(ev_list))
            for sent in ev_list:
                if not sent:
                    continue
                substring_total += 1
                if md_text and is_verbatim_in_md(str(sent), md_text):
                    substring_hits += 1
                    paper_substring_hits += 1

        stats["papers"] += 1
        stats["experiments"] += exp_count
        stats["evidence_sentences_total"] += paper_evidence
        if exp_count > 1:
            stats["multi_experiment_paper_ids"].append(paper_id)

    if evidence_counts:
        stats["evidence_per_experiment"] = {
            "min": min(evidence_counts),
            "max": max(evidence_counts),
            "median": round(statistics.median(evidence_counts), 2),
        }
    else:
        stats["evidence_per_experiment"] = {"min": 0, "max": 0, "median": 0}

    stats["gold_substring_rate"] = (
        round(substring_hits / substring_total, 4) if substring_total else 0.0
    )
    stats["gold_substring_hits"] = substring_hits
    stats["gold_substring_total"] = substring_total
    stats["wall_ms"] = round((time.perf_counter() - t0) * 1000, 2)

    stats_path = out_base / "build_stats.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Build evidence gold sets")
    parser.add_argument("--batch", default="dev_10")
    args = parser.parse_args()

    stats = build_gold_sets(args.batch, project_root)
    print(f"Built gold for {stats['papers']} papers, {stats['experiments']} experiments")
    print(f"  evidence sentences: {stats['evidence_sentences_total']}")
    print(f"  gold_substring_rate: {stats['gold_substring_rate']:.2%}")
    if stats["multi_experiment_paper_ids"]:
        print(f"  multi-experiment papers: {stats['multi_experiment_paper_ids']}")


if __name__ == "__main__":
    main()
