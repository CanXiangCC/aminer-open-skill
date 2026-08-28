"""
Datasets字段测试运行器 - Datasets Field Test Runner

支持 Gold1/Gold2、v1-v4 策略、strict/fuzzy/semantic 评估、runs/{run_id}/ 可复盘目录。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import experiments.rule_extraction.datasets.strategies.v1_section_table as v1_module
import experiments.rule_extraction.datasets.strategies.v2_keyword_fulltext as v2_module
import experiments.rule_extraction.datasets.strategies.v3_gazetteer as v3_module
import experiments.rule_extraction.datasets.strategies.v4_layered as v4_module
import experiments.rule_extraction.datasets.strategies.v4_1_layered as v41_module
import experiments.rule_extraction.datasets.strategies.v4_2_union as v42_module
import experiments.rule_extraction.datasets.strategies.v4_3_union as v43_module
import experiments.rule_extraction.datasets.strategies.v4_3_1_union as v431_module
import experiments.rule_extraction.datasets.strategies.v4_5_union as v45_module
import experiments.rule_extraction.datasets.strategies.v4_6_union as v46_module
from experiments.rule_extraction.datasets.shared.dataset_evaluator import (
    aggregate_evaluations,
    evaluate_paper_datasets,
)
from experiments.rule_extraction.datasets.analysis.generate_comparison import generate_all
from experiments.rule_extraction.datasets.assignment import (
    ASSIGN_STRATEGIES,
    ASSIGN_STRATEGY_NAMES,
    run_assignment,
)
from experiments.rule_extraction.datasets.assignment.evaluator import evaluate_assignment
from src.evaluation.semantic import SemanticScorer

DATASETS_ROOT = Path(__file__).parent
STRATEGIES = {
    "v1": v1_module.DatasetRuleV1,
    "v2": v2_module.DatasetRuleV2,
    "v3": v3_module.DatasetRuleV3,
    "v4": v4_module.DatasetRuleV4,
    "v4_1": v41_module.DatasetRuleV41,
    "v4_2": v42_module.DatasetRuleV42,
    "v4_3": v43_module.DatasetRuleV43,
    "v4_3_1": v431_module.DatasetRuleV431,
    "v4_5": v45_module.DatasetRuleV45,
    "v4_6": v46_module.DatasetRuleV46,
}
STRATEGY_NAMES = {
    "v1": "datasets--策略v1--Section+Table提取 (Layer 2)",
    "v2": "datasets--策略v2--关键词全文匹配 (Layer 1)",
    "v3": "datasets--策略v3--Gazetteer验证 (强语境正则+白名单+黑名单)",
    "v4": "datasets--策略v4--分层混合 (Layer A/B + Gazetteer软标注)",
    "v4_1": "datasets--策略v4.1--分层混合收紧 (无camel_case+语境abbrev+dataset标题表格)",
    "v4_2": "datasets--策略v4.2--Union (v4.1 ∪ v4宽松→Gazetteer硬过滤)",
    "v4_3": "datasets--策略v4.3--Union收紧 (v4.2+ChannelB语境过滤+Gazetteer扩充)",
    "v4_3_1": "datasets--策略v4.3.1--Union收紧+硬过滤强化 (无Gazetteer扩充)",
    "v4_5": "datasets--策略v4.5--Union (Branch B tight + Hybrid gazetteer)",
    "v4_6": "datasets--策略v4.6--Union (Branch B tiered match + Hybrid gazetteer)",
}
TRACE_STRATEGIES = {"v3", "v4", "v4_1", "v4_2", "v4_3", "v4_3_1", "v4_5", "v4_6"}
DEFAULT_EVAL_MODES = ["strict", "fuzzy", "semantic"]


def _git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=5,
            check=False,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return None


def load_gold_data(batch: str = "dev_10", gold_set: str = "paper_union") -> dict[str, list[dict[str, Any]]]:
    """Load gold datasets (flat list per paper) for the extract-stage evaluator.

    For `paper_union`: returns Gold2 union datasets per paper.
    For `per_experiment`: returns the union of all experiments' datasets per
    paper (deduped by normalized name). This fixes the prior bug where only
    the first experiment with datasets was used, which silently dropped
    datasets belonging to later experiments (e.g. HighD in `6632f3d20`).

    For assignment evaluation use `load_gold_experiments` / `load_gold_experiments_stripped`
    which preserve the full experiment array structure.
    """
    if gold_set == "per_experiment":
        gold_dir = DATASETS_ROOT / "data" / "gold" / batch / "per_experiment"
        gold_data: dict[str, list[dict[str, Any]]] = {}
        for json_file in gold_dir.glob("*.json"):
            paper_id = json_file.stem
            with open(json_file, encoding="utf-8") as f:
                data = json.load(f)
            experiments = data if isinstance(data, list) else [data]
            # Union datasets across all experiments, dedup by normalized name.
            seen: dict[str, dict[str, Any]] = {}
            for exp in experiments:
                datasets = exp.get("datasets")
                if not isinstance(datasets, list):
                    continue
                for ds in datasets:
                    name = (ds.get("name") or "").strip() if isinstance(ds, dict) else ""
                    key = (ds.get("name") or "").lower().strip()
                    if not key:
                        continue
                    if key not in seen:
                        seen[key] = ds
            gold_data[paper_id] = list(seen.values())
        return gold_data

    gold_dir = DATASETS_ROOT / "data" / "gold" / batch / "paper_union"
    gold_data = {}
    for json_file in gold_dir.glob("*.json"):
        paper_id = json_file.stem
        with open(json_file, encoding="utf-8") as f:
            doc = json.load(f)
        gold_data[paper_id] = doc.get("datasets") or []
    return gold_data


def load_gold_experiments(batch: str = "dev_10") -> dict[str, list[dict[str, Any]]]:
    """Load Gold1 full experiment arrays per paper (with gold `datasets` intact).

    Used by assignment evaluation as the gold side.
    """
    gold_dir = DATASETS_ROOT / "data" / "gold" / batch / "per_experiment"
    out: dict[str, list[dict[str, Any]]] = {}
    for json_file in gold_dir.glob("*.json"):
        paper_id = json_file.stem
        with open(json_file, encoding="utf-8") as f:
            data = json.load(f)
        out[paper_id] = data if isinstance(data, list) else [data]
    return out


def load_gold_experiments_stripped(batch: str = "dev_10") -> dict[str, list[dict[str, Any]]]:
    """Load Gold1 experiments with the `datasets` field removed.

    This is the assignment input: experiment metadata only, no gold leakage.
    """
    out = load_gold_experiments(batch)
    for paper_id, exps in out.items():
        stripped = []
        for exp in exps:
            e = {k: v for k, v in exp.items() if k != "datasets"}
            stripped.append(e)
        out[paper_id] = stripped
    return out


def load_gold_stats(batch: str = "dev_10") -> dict[str, Any]:
    stats_path = DATASETS_ROOT / "data" / "gold" / batch / "build_stats.json"
    if stats_path.exists():
        with open(stats_path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_manifest(batch: str = "dev_10") -> list[dict[str, Any]]:
    manifest_path = project_root / "data" / "fixtures" / batch / "manifest.json"
    with open(manifest_path, encoding="utf-8") as f:
        return json.load(f)


def _extract_strategy(strategy_id: str, strategy_class: type, md_text: str, paper_id: str) -> tuple[list[dict], dict]:
    result = strategy_class.extract(md_text, paper_id)
    if strategy_id in TRACE_STRATEGIES:
        if isinstance(result, dict):
            return result.get("datasets") or [], result.get("trace") or {}
        return [], {}
    return (result or []), {}


def run_strategy_test(
    strategy_id: str,
    gold_data: dict[str, list[dict]],
    manifest: list[dict[str, Any]],
    *,
    eval_modes: list[str],
    semantic_scorer: SemanticScorer | None,
    run_dir: Path | None = None,
) -> dict[str, Any]:
    strategy_class = STRATEGIES[strategy_id]
    results: dict[str, Any] = {
        "strategy_id": strategy_id,
        "strategy_name": STRATEGY_NAMES[strategy_id],
        "test_time": datetime.now().isoformat(),
        "batch": "dev_10",
        "eval_modes": eval_modes,
        "papers": [],
    }

    paper_evals: list[dict[str, Any]] = []
    timings: list[dict[str, float]] = []

    for item in manifest:
        paper_id = item["paper_id"]
        gold_datasets = gold_data.get(paper_id)
        if not gold_datasets:
            continue

        try:
            md_path = item.get("md_path", "")
            md_full_path = project_root / md_path
            md_text = md_full_path.read_text(encoding="utf-8")

            t0 = time.perf_counter()
            rule_datasets, trace = _extract_strategy(strategy_id, strategy_class, md_text, paper_id)
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

            evaluation = evaluate_paper_datasets(
                gold_datasets,
                rule_datasets or [],
                semantic_scorer=semantic_scorer if "semantic" in eval_modes else None,
            )

            paper_record: dict[str, Any] = {
                "paper_id": paper_id,
                "gold_count": evaluation["gold_count"],
                "rule_count": evaluation["rule_count"],
                "evaluation": {
                    mode: evaluation[mode] for mode in eval_modes if mode in evaluation
                },
                "match_pairs": evaluation.get("match_pairs", []),
                "gold": gold_datasets,
                "rule": rule_datasets,
                "success": bool(rule_datasets),
                "trace": trace,
                "extract_ms": elapsed_ms,
            }

            # Legacy fields from strict for backward compat
            st = evaluation["strict"]
            paper_record.update({
                "matched_count": st["matched_count"],
                "missed_count": st["missed_count"],
                "extra_count": st["extra_count"],
                "recall": st["recall"],
                "precision": st["precision"],
                "gold_names": st.get("missed_names", []) + st.get("matched_names", []),
                "rule_names": st.get("extra_names", []) + st.get("matched_names", []),
                "matched_names": st.get("matched_names", []),
                "missed_names": st.get("missed_names", []),
                "extra_names": st.get("extra_names", []),
            })

            results["papers"].append(paper_record)
            paper_evals.append(evaluation)

            if trace.get("timing_ms"):
                timings.append(trace["timing_ms"])
            elif strategy_id in ("v4", "v4_1", "v4_2", "v4_3", "v4_3_1", "v4_5", "v4_6"):
                timings.append({"strategy_total": elapsed_ms})

            if run_dir and strategy_id in TRACE_STRATEGIES:
                trace_dir = run_dir / "traces" / strategy_id
                trace_dir.mkdir(parents=True, exist_ok=True)
                with open(trace_dir / f"{paper_id}.json", "w", encoding="utf-8") as f:
                    json.dump({"paper_id": paper_id, "trace": trace, "rule": rule_datasets}, f, indent=2, ensure_ascii=False)

        except Exception as e:
            results["papers"].append({
                "paper_id": paper_id,
                "gold": gold_datasets,
                "rule": None,
                "success": False,
                "error": str(e),
                "trace": {},
            })

    summary: dict[str, Any] = {}
    for mode in eval_modes:
        summary[mode] = aggregate_evaluations(paper_evals, mode)

    # Primary summary = fuzzy (default for rule exploration)
    primary = summary.get("fuzzy") or summary.get("strict", {})
    results["summary"] = {
        **primary,
        "by_mode": summary,
    }

    if timings and strategy_id in TRACE_STRATEGIES:
        totals = [t.get("strategy_total", 0) for t in timings]
        results["timing_summary"] = {
            "mean_strategy_total_ms": round(sum(totals) / len(totals), 2),
            "p95_strategy_total_ms": round(sorted(totals)[int(len(totals) * 0.95)], 2) if totals else 0,
        }

    return results


def run_assignment_test(
    extract_strategy_id: str,
    assign_strategy_id: str,
    gold_experiments: dict[str, list[dict[str, Any]]],
    experiments_stripped: dict[str, list[dict[str, Any]]],
    manifest: list[dict[str, Any]],
    *,
    eval_modes: list[str],
    semantic_scorer: SemanticScorer | None,
    run_dir: Path | None = None,
    multi_experiment_paper_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Run extract (v4.3) → assign → per-experiment evaluate for each paper.

    Produces a results dict shaped like `run_strategy_test` but at experiment
    granularity, plus per-paper assignment traces written to
    `runs/{run_id}/traces/{assign_strategy_id}/{paper_id}.json`.
    """
    extract_class = STRATEGIES[extract_strategy_id]
    assign_strategy = ASSIGN_STRATEGIES[assign_strategy_id]()

    results: dict[str, Any] = {
        "extract_strategy_id": extract_strategy_id,
        "assign_strategy_id": assign_strategy_id,
        "assign_strategy_name": ASSIGN_STRATEGY_NAMES[assign_strategy_id],
        "test_time": datetime.now().isoformat(),
        "batch": "dev_10",
        "eval_modes": eval_modes,
        "papers": [],
    }

    assigned_by_paper: dict[str, list[dict[str, Any]]] = {}
    extract_traces: dict[str, dict[str, Any]] = {}

    for item in manifest:
        paper_id = item["paper_id"]
        if paper_id not in gold_experiments:
            continue
        try:
            md_path = item.get("md_path", "")
            md_text = (project_root / md_path).read_text(encoding="utf-8")

            # Stage 1: paper-level extract.
            t0 = time.perf_counter()
            ext_out = extract_class.extract(md_text, paper_id)
            if isinstance(ext_out, dict):
                paper_datasets = ext_out.get("datasets") or []
                ext_trace = ext_out.get("trace") or {}
            else:
                paper_datasets = ext_out or []
                ext_trace = {}
            extract_ms = round((time.perf_counter() - t0) * 1000, 2)

            # Stage 2: per-experiment assignment.
            exps_stripped = experiments_stripped.get(paper_id) or []
            t1 = time.perf_counter()
            assigned = run_assignment(
                assign_strategy,
                paper_datasets,
                exps_stripped,
                md_text,
                paper_id=paper_id,
            )
            assign_ms = round((time.perf_counter() - t1) * 1000, 2)

            assigned_by_paper[paper_id] = assigned
            extract_traces[paper_id] = {
                "extract_ms": extract_ms,
                "assign_ms": assign_ms,
                "paper_dataset_count": len(paper_datasets),
                "extract_trace": ext_trace,
            }

            # Per-paper trace dump.
            if run_dir is not None:
                trace_dir = run_dir / "traces" / assign_strategy_id
                trace_dir.mkdir(parents=True, exist_ok=True)
                with open(trace_dir / f"{paper_id}.json", "w", encoding="utf-8") as f:
                    json.dump({
                        "paper_id": paper_id,
                        "paper_datasets": paper_datasets,
                        "assigned_experiments": assigned,
                        "extract_ms": extract_ms,
                        "assign_ms": assign_ms,
                    }, f, indent=2, ensure_ascii=False)

            results["papers"].append({
                "paper_id": paper_id,
                "experiment_count": len(assigned),
                "paper_dataset_count": len(paper_datasets),
                "extract_ms": extract_ms,
                "assign_ms": assign_ms,
                "assigned": assigned,
            })
        except Exception as e:
            results["papers"].append({
                "paper_id": paper_id,
                "error": str(e),
                "success": False,
            })

    # Stage 3: evaluate at experiment granularity.
    eval_result = evaluate_assignment(
        assigned_by_paper,
        gold_experiments,
        eval_modes=eval_modes,
        multi_experiment_paper_ids=multi_experiment_paper_ids,
    )
    results["summary"] = {
        "overall": eval_result["overall"],
        "multi_experiment": eval_result["multi_experiment"],
        "stats": eval_result["stats"],
    }
    results["per_experiment"] = eval_result["per_experiment"]
    return results


def save_result(results: dict[str, Any], strategy_id: str, run_dir: Path, *, filename: str | None = None) -> Path:
    output_dir = run_dir / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / (filename or f"{strategy_id}_on_dev10.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    return output_file


def _write_step(run_dir: Path, name: str, payload: dict[str, Any]) -> None:
    steps_dir = run_dir / "steps"
    steps_dir.mkdir(parents=True, exist_ok=True)
    with open(steps_dir / name, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def ensure_gold_built(batch: str, run_dir: Path) -> dict[str, Any]:
    stats_path = DATASETS_ROOT / "data" / "gold" / batch / "build_stats.json"
    if not stats_path.exists():
        from experiments.rule_extraction.datasets.scripts.build_gold_sets import build_gold_sets
        stats = build_gold_sets(batch, project_root)
    else:
        with open(stats_path, encoding="utf-8") as f:
            stats = json.load(f)
    _write_step(run_dir, "01_build_gold.json", stats)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Run datasets extraction tests")
    parser.add_argument("--strategy", choices=list(STRATEGIES.keys()))
    parser.add_argument("--compare-all", action="store_true")
    parser.add_argument("--batch", default="dev_10")
    parser.add_argument("--gold-set", default="paper_union", choices=["paper_union", "per_experiment"])
    parser.add_argument("--run-id", default=None, help="Run ID (default: timestamp)")
    parser.add_argument("--eval-modes", default="strict,fuzzy,semantic")
    parser.add_argument("--semantic-type", default="jaccard", choices=["embedding", "jaccard"])
    parser.add_argument("--rebuild-gold", action="store_true")
    parser.add_argument(
        "--gazetteer-path",
        default=None,
        help="Path to a gazetteer JSON to use instead of the default gazetteer.json. "
             "Sets the RULE_GAZETTEER_PATH env var for both the strategy and the evaluator.",
    )
    parser.add_argument(
        "--stage",
        choices=["extract", "assign", "both"],
        default="extract",
        help="extract = paper-level only (legacy flow); assign/both = v4.3 extract → "
             "assign → per-experiment evaluate (requires --gold-set per_experiment).",
    )
    parser.add_argument("--extract-strategy", default="v4_3", choices=list(STRATEGIES.keys()))
    parser.add_argument(
        "--assign-strategy",
        default="v2_type_aware",
        choices=list(ASSIGN_STRATEGIES.keys()),
    )
    args = parser.parse_args()

    if args.gazetteer_path:
        import os
        os.environ["RULE_GAZETTEER_PATH"] = str(Path(args.gazetteer_path).resolve())
        print(f"Using gazetteer: {os.environ['RULE_GAZETTEER_PATH']}")

    # Resolve effective extract strategy: --extract-strategy wins, falls back to --strategy.
    extract_strategy = args.extract_strategy or args.strategy or "v4_3"

    eval_modes = [m.strip() for m in args.eval_modes.split(",") if m.strip()]
    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = DATASETS_ROOT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    timeline: list[dict[str, Any]] = []
    t_run_start = time.perf_counter()

    if args.rebuild_gold:
        from experiments.rule_extraction.datasets.scripts.build_gold_sets import build_gold_sets
        gold_stats = build_gold_sets(args.batch, project_root)
    else:
        gold_stats = ensure_gold_built(args.batch, run_dir)

    semantic_scorer = None
    semantic_config = {"type": args.semantic_type}
    if "semantic" in eval_modes:
        semantic_scorer = SemanticScorer(type=args.semantic_type)
        semantic_config = semantic_scorer.to_config()

    # Dispatch by stage.
    run_assignment_stage = args.stage in ("assign", "both")
    if run_assignment_stage and args.gold_set != "per_experiment":
        print("WARNING: --stage assign/both requires --gold-set per_experiment; "
              "auto-switching gold_set to per_experiment.")
        args.gold_set = "per_experiment"

    t0 = time.perf_counter()
    manifest = load_manifest(args.batch)
    if run_assignment_stage:
        gold_experiments = load_gold_experiments(args.batch)
        experiments_stripped = load_gold_experiments_stripped(args.batch)
        multi_exp_ids = list(gold_stats.get("multi_experiment_papers") or [])
    else:
        gold_data = load_gold_data(args.batch, args.gold_set)
    timeline.append({"step": "load_data", "duration_ms": round((time.perf_counter() - t0) * 1000, 2), "status": "ok"})

    all_results: dict[str, dict[str, Any]] = {}

    if run_assignment_stage:
        t_step = time.perf_counter()
        print(f"\nTesting assignment: extract={extract_strategy} assign={args.assign_strategy}...")
        results = run_assignment_test(
            extract_strategy,
            args.assign_strategy,
            gold_experiments,
            experiments_stripped,
            manifest,
            eval_modes=eval_modes,
            semantic_scorer=semantic_scorer,
            run_dir=run_dir,
            multi_experiment_paper_ids=multi_exp_ids,
        )
        results["batch"] = args.batch
        out_filename = f"assign_{args.assign_strategy}_on_{args.batch}.json"
        out_path = save_result(results, args.assign_strategy, run_dir, filename=out_filename)
        all_results[args.assign_strategy] = results
        overall = results["summary"]["overall"]
        fuzzy = overall.get("fuzzy", {})
        multi = results["summary"]["multi_experiment"].get("fuzzy", {})
        stats = results["summary"]["stats"]
        print(
            f"  overall fuzzy: R={fuzzy.get('recall', 0):.2%} P={fuzzy.get('precision', 0):.2%} "
            f"F1={fuzzy.get('f1', 0):.2%}"
        )
        print(
            f"  multi-experiment fuzzy: R={multi.get('recall', 0):.2%} "
            f"P={multi.get('precision', 0):.2%} F1={multi.get('f1', 0):.2%} "
            f"({stats.get('multi_experiment_count', 0)} exps)"
        )
        print(f"  broadcast triggered: {stats.get('broadcast_trigger_count', 0)} exps "
              f"across {len(stats.get('broadcast_papers', []))} papers")
        print(f"  -> {out_path}")
        _write_step(run_dir, "02_run_assignment.json", {
            "extract_strategy_id": extract_strategy,
            "assign_strategy_id": args.assign_strategy,
            "duration_ms": round((time.perf_counter() - t_step) * 1000, 2),
            "summary": results["summary"],
            "output": str(out_path),
        })
        timeline.append({
            "step": "run_assignment",
            "duration_ms": round((time.perf_counter() - t_step) * 1000, 2),
            "status": "ok",
        })
        strategies_to_run = [args.assign_strategy]
    else:
        strategies_to_run = list(STRATEGIES.keys()) if args.compare_all else ([args.strategy] if args.strategy else [])
        if not strategies_to_run:
            parser.print_help()
            return
        for i, strategy_id in enumerate(strategies_to_run, start=2):
            step_name = f"{i:02d}_run_{strategy_id}.json"
            t_step = time.perf_counter()
            print(f"\nTesting {STRATEGY_NAMES[strategy_id]}...")
            results = run_strategy_test(
                strategy_id,
                gold_data,
                manifest,
                eval_modes=eval_modes,
                semantic_scorer=semantic_scorer,
                run_dir=run_dir,
            )
            results["batch"] = args.batch
            out_path = save_result(results, strategy_id, run_dir)
            all_results[strategy_id] = results
            by_mode = results["summary"].get("by_mode", {})
            fuzzy = by_mode.get("fuzzy", results["summary"])
            print(
                f"  fuzzy: R={fuzzy['recall']:.2%} P={fuzzy['precision']:.2%} F1={fuzzy['f1']:.2%} "
                f"-> {out_path}"
            )
            _write_step(run_dir, step_name, {
                "strategy_id": strategy_id,
                "duration_ms": round((time.perf_counter() - t_step) * 1000, 2),
                "summary_by_mode": by_mode,
                "output": str(out_path),
            })
            timeline.append({
                "step": f"run_{strategy_id}",
                "duration_ms": round((time.perf_counter() - t_step) * 1000, 2),
                "status": "ok",
            })

    if args.compare_all and not run_assignment_stage and len(all_results) > 1:
        t_rep = time.perf_counter()
        report_paths = generate_all(run_dir, args.gold_set)
        _write_step(run_dir, f"{len(strategies_to_run)+2:02d}_generate_report.json", {
            "duration_ms": round((time.perf_counter() - t_rep) * 1000, 2),
            "paths": report_paths,
        })
        timeline.append({"step": "generate_report", "duration_ms": round((time.perf_counter() - t_rep) * 1000, 2), "status": "ok"})
        print(f"\nReports written under {run_dir / 'analysis'}")

    manifest_doc = {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(),
        "git_commit": _git_commit(),
        "batch": args.batch,
        "gold_set": args.gold_set,
        "stage": args.stage,
        "extract_strategy": extract_strategy if run_assignment_stage else None,
        "assign_strategy": args.assign_strategy if run_assignment_stage else None,
        "gazetteer_path": str(Path(args.gazetteer_path).resolve()) if args.gazetteer_path else None,
        "gold_stats": gold_stats,
        "eval_modes": eval_modes,
        "semantic_config": semantic_config,
        "strategies": strategies_to_run,
        "summary": {
            sid: (all_results[sid]["summary"].get("by_mode", {})
                  if "by_mode" in all_results[sid]["summary"]
                  else all_results[sid]["summary"])
            for sid in all_results
        },
        "step_timeline": timeline,
        "total_duration_ms": round((time.perf_counter() - t_run_start) * 1000, 2),
        "run_dir": str(run_dir),
    }
    with open(run_dir / "run_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest_doc, f, indent=2, ensure_ascii=False)

    print(f"\nRun manifest: {run_dir / 'run_manifest.json'}")


if __name__ == "__main__":
    main()
