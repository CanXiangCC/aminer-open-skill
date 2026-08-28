"""
Generate comparison reports from a datasets evaluation run directory.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


STRATEGY_ORDER = ["v1", "v2", "v3", "v4", "v4_1", "v4_2", "v4_3", "v4_3_1", "v4_5", "v4_6"]
STRATEGY_LABELS = {
    "v1": "v1 Section+Table",
    "v2": "v2 Keyword Fulltext",
    "v3": "v3 Gazetteer Hard Filter",
    "v4": "v4 Layered Hybrid",
    "v4_1": "v4.1 Layered Tight",
    "v4_2": "v4.2 Union",
    "v4_3": "v4.3 Union Tight",
    "v4_3_1": "v4.3.1 Tight NoExp",
    "v4_5": "v4.5 Tight Hybrid",
    "v4_6": "v4.6 Tiered Hybrid",
}
SURVEY_PAPER = "5b1643ba8fbcbf6e5a9bc884"
EVAL_MODES = ["strict", "fuzzy", "semantic"]


def _load_results(run_dir: Path) -> dict[str, dict[str, Any]]:
    results_dir = run_dir / "results"
    out: dict[str, dict[str, Any]] = {}
    for sid in STRATEGY_ORDER:
        path = results_dir / f"{sid}_on_dev10.json"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                out[sid] = json.load(f)
    return out


def _fmt_pct(v: float) -> str:
    return f"{v:.2%}"


def generate_comparison(run_dir: Path, gold_set: str = "paper_union") -> Path:
    all_results = _load_results(run_dir)
    analysis_dir = run_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Datasets 策略对比 (v1-v4)\n",
        f"生成时间: {datetime.now().isoformat()}\n",
        f"Run 目录: `{run_dir}`\n",
        f"Gold 集合: **{gold_set}**\n",
    ]

    for mode in EVAL_MODES:
        lines.append(f"\n## 指标: {mode}\n")
        lines.append(
            "| 策略 | Recall | Precision | F1 | Gold | 提取 | 匹配 | 漏抽 | 多抽 |\n"
        )
        lines.append("|------|--------|-----------|----|----|------|------|------|------|\n")
        for sid in STRATEGY_ORDER:
            if sid not in all_results:
                continue
            s = all_results[sid]["summary"].get(mode, all_results[sid]["summary"])
            lines.append(
                f"| {STRATEGY_LABELS[sid]} | {_fmt_pct(s['recall'])} | "
                f"{_fmt_pct(s['precision'])} | {_fmt_pct(s['f1'])} | "
                f"{s.get('total_gold_datasets', 0)} | {s.get('total_rule_datasets', 0)} | "
                f"{s.get('total_matched', 0)} | {s.get('total_missed', 0)} | "
                f"{s.get('total_extra', 0)} |\n"
            )

    if "v4" in all_results:
        ts = all_results["v4"].get("timing_summary", {})
        if ts:
            lines.append("\n## v4 Timing\n")
            lines.append(f"- 平均总耗时: {ts.get('mean_strategy_total_ms', 0):.2f} ms\n")
            lines.append(f"- P95: {ts.get('p95_strategy_total_ms', 0):.2f} ms\n")

    out_path = analysis_dir / "comparison.md"
    out_path.write_text("".join(lines), encoding="utf-8")
    return out_path


def generate_per_paper_breakdown(run_dir: Path) -> Path:
    all_results = _load_results(run_dir)
    analysis_dir = run_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    paper_ids: list[str] = []
    if all_results:
        first = next(iter(all_results.values()))
        paper_ids = [p["paper_id"] for p in first.get("papers", [])]

    lines = ["# 逐篇评估明细\n", f"生成时间: {datetime.now().isoformat()}\n"]

    for pid in paper_ids:
        survey = " [SURVEY]" if pid == SURVEY_PAPER else ""
        lines.append(f"\n## {pid}{survey}\n")
        for mode in EVAL_MODES:
            lines.append(f"\n### {mode}\n")
            lines.append("| 策略 | R | P | F1 | matched | missed | extra |\n")
            lines.append("|------|---|---|-----|---------|--------|-------|\n")
            for sid in STRATEGY_ORDER:
                if sid not in all_results:
                    continue
                paper = next((p for p in all_results[sid]["papers"] if p["paper_id"] == pid), None)
                if not paper:
                    continue
                ev = paper.get("evaluation", paper)
                m = ev.get(mode, ev)
                lines.append(
                    f"| {sid} | {_fmt_pct(m.get('recall', 0))} | {_fmt_pct(m.get('precision', 0))} | "
                    f"{_fmt_pct(m.get('f1', 0))} | {m.get('matched_count', 0)} | "
                    f"{m.get('missed_count', 0)} | {m.get('extra_count', 0)} |\n"
                )

    # Survey vs non-survey aggregate for v4 fuzzy
    lines.append("\n## 分组统计 (fuzzy)\n")
    for label, pred in [("Survey", lambda p: p == SURVEY_PAPER), ("Non-Survey", lambda p: p != SURVEY_PAPER)]:
        lines.append(f"\n### {label}\n")
        lines.append("| 策略 | Recall | Precision | F1 |\n")
        lines.append("|------|--------|-----------|----|\n")
        for sid in STRATEGY_ORDER:
            if sid not in all_results:
                continue
            papers = [p for p in all_results[sid]["papers"] if pred(p["paper_id"])]
            tg = sum(p["gold_count"] for p in papers)
            tr = sum(p["rule_count"] for p in papers)
            tm = sum(p.get("evaluation", p).get("fuzzy", {}).get("matched_count", 0) for p in papers)
            recall = tm / tg if tg else 0
            precision = tm / tr if tr else 0
            f1 = 2 * recall * precision / (recall + precision) if (recall + precision) else 0
            lines.append(f"| {sid} | {_fmt_pct(recall)} | {_fmt_pct(precision)} | {_fmt_pct(f1)} |\n")

    out_path = analysis_dir / "per_paper_breakdown.md"
    out_path.write_text("".join(lines), encoding="utf-8")
    return out_path


def generate_all(run_dir: Path, gold_set: str = "paper_union") -> dict[str, str]:
    comparison = generate_comparison(run_dir, gold_set)
    breakdown = generate_per_paper_breakdown(run_dir)

    v4_report_src = Path(__file__).parent.parent / "strategies" / "v4_report.md"
    v4_report_dst = run_dir / "analysis" / "v4_report.md"
    if v4_report_src.exists():
        v4_report_dst.write_text(v4_report_src.read_text(encoding="utf-8"), encoding="utf-8")

    v41_report_src = Path(__file__).parent.parent / "strategies" / "v4_1_report.md"
    v41_report_dst = run_dir / "analysis" / "v4_1_report.md"
    if v41_report_src.exists():
        v41_report_dst.write_text(v41_report_src.read_text(encoding="utf-8"), encoding="utf-8")

    v42_report_src = Path(__file__).parent.parent / "strategies" / "v4_2_report.md"
    v42_report_dst = run_dir / "analysis" / "v4_2_report.md"
    if v42_report_src.exists():
        v42_report_dst.write_text(v42_report_src.read_text(encoding="utf-8"), encoding="utf-8")

    v43_report_src = Path(__file__).parent.parent / "strategies" / "v4_3_report.md"
    v43_report_dst = run_dir / "analysis" / "v4_3_report.md"
    if v43_report_src.exists():
        v43_report_dst.write_text(v43_report_src.read_text(encoding="utf-8"), encoding="utf-8")

    v431_report_src = Path(__file__).parent.parent / "strategies" / "v4_3_1_report.md"
    v431_report_dst = run_dir / "analysis" / "v4_3_1_report.md"
    if v431_report_src.exists():
        v431_report_dst.write_text(v431_report_src.read_text(encoding="utf-8"), encoding="utf-8")

    return {
        "comparison": str(comparison),
        "per_paper_breakdown": str(breakdown),
        "v4_report": str(v4_report_dst),
        "v4_1_report": str(v41_report_dst),
        "v4_2_report": str(v42_report_dst),
        "v4_3_report": str(v43_report_dst),
        "v4_3_1_report": str(v431_report_dst),
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--gold-set", default="paper_union")
    args = parser.parse_args()
    paths = generate_all(Path(args.run_dir), args.gold_set)
    for k, v in paths.items():
        print(f"{k}: {v}")
