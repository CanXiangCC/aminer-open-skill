"""
Limitations字段测试运行器 - Limitations Field Test Runner
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import experiments.rule_extraction.limitations.strategies.v1_section_extract as v1_module
import experiments.rule_extraction.limitations.strategies.v2_conclusion_search as v2_module
import experiments.rule_extraction.limitations.strategies.v3_fuzzy_match as v3_module
import experiments.rule_extraction.limitations.strategies.v4_multi_source as v4_module
import experiments.rule_extraction.limitations.strategies.v5_layered as v5_module
import experiments.rule_extraction.limitations.strategies.vA_conditional as vA_module
import experiments.rule_extraction.limitations.strategies.vB_enhanced_v1 as vB_module
import experiments.rule_extraction.limitations.strategies.vC_conclusion_tail as vC_module
import experiments.rule_extraction.limitations.strategies.vD_conclusion_signals as vD_module
import experiments.rule_extraction.limitations.strategies.vE_improved_vD as vE_module
import experiments.rule_extraction.limitations.strategies.vF_preprocess_vE as vF_module
import experiments.rule_extraction.limitations.strategies.vG_only_refs_vD as vG_module
import experiments.rule_extraction.limitations.strategies.vH_enhanced_refs as vH_module
import experiments.rule_extraction.limitations.strategies.vI_self_refer_no_layer3 as vI_module
import experiments.rule_extraction.limitations.strategies.vJ_strict_filter as vJ_module
import experiments.rule_extraction.limitations.strategies.vK_enhanced_filter as vK_module

STRATEGIES = {
    "v1": v1_module.LimitationsRuleV1,
    "v2": v2_module.LimitationsRuleV2,
    "v3": v3_module.LimitationsRuleV3,
    "v4": v4_module.LimitationsRuleV4,
    "v5": v5_module.LimitationsRuleV5,
    "vA": vA_module.LimitationsRuleA,
    "vB": vB_module.LimitationsRuleB,
    "vC": vC_module.LimitationsRuleC,
    "vD": vD_module.LimitationsRuleD,
    "vE": vE_module.LimitationsRuleE,
    "vF": vF_module.LimitationsRuleF,
    "vG": vG_module.LimitationsRuleG,
    "vH": vH_module.LimitationsRuleH,
    "vI": vI_module.LimitationsRuleI,
    "vJ": vJ_module.LimitationsRuleJ,
    "vK": vK_module.LimitationsRuleK,
}

STRATEGY_NAMES = {
    "v1": "limitations--策略v1--section提取",
    "v2": "limitations--策略v2--conclusion内搜索",
    "v3": "limitations--策略v3--全文模糊匹配",
    "v4": "limitations--策略v4--多源融合",
    "v5": "limitations--策略v5--三层分层",
    "vA": "limitations--策略A--条件式v1+v2",
    "vB": "limitations--策略B--增强v1+Conclusion",
    "vC": "limitations--策略C--Conclusion末尾找",
    "vD": "limitations--策略D--Conclusion信号句",
    "vE": "limitations--策略E--改进vD（后20%fallback）",
    "vF": "limitations--策略F--预处理vE（删除Introduction/References）",
    "vG": "limitations--策略G--只删除References（保持vD逻辑）",
    "vH": "limitations--策略H--增强引用删除（混杂引用检测）",
    "vI": "limitations--策略I--自指验证+精简信号词+取消Layer3",
    "vJ": "limitations--策略J--vH+严格过滤（排除表格/Future Work/积极内容）",
    "vK": "limitations--策略K--vJ增强过滤（方法介绍/对比工作/消极词验证/自指验证）",
}


def load_gold_data(batch: str = "dev_10") -> Dict[str, str]:
    """加载Gold标准的limitations数据"""
    gold_dir = project_root / "data" / "gold" / batch / "full_text_glm5_2"
    gold_data = {}

    for json_file in gold_dir.glob("*.json"):
        paper_id = json_file.stem
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                experiments = data if isinstance(data, list) else [data]
                for exp in experiments:
                    limitations = exp.get("limitations")
                    if limitations:
                        gold_data[paper_id] = limitations
                        break
        except Exception as e:
            print(f"Error loading {json_file}: {e}")

    return gold_data


def load_manifest(batch: str = "dev_10") -> List[Dict[str, Any]]:
    """加载manifest文件"""
    manifest_path = project_root / "data" / "fixtures" / batch / "manifest.json"
    with open(manifest_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_paper_md(md_path: str) -> str:
    """加载论文markdown"""
    full_path = project_root / md_path
    with open(full_path, 'r', encoding='utf-8') as f:
        return f.read()


def run_strategy_test(strategy_id: str, gold_data: Dict[str, str], manifest: List[Dict[str, Any]]) -> Dict[str, Any]:
    """运行单个策略测试"""
    strategy_class = STRATEGIES[strategy_id]
    results = {
        "strategy_id": strategy_id,
        "strategy_name": STRATEGY_NAMES[strategy_id],
        "test_time": datetime.now().isoformat(),
        "batch": "dev_10",
        "papers": []
    }

    success_count = 0
    fail_count = 0

    for item in manifest:
        paper_id = item["paper_id"]
        gold_limitations = gold_data.get(paper_id)

        if gold_limitations is None:
            continue

        try:
            md_text = load_paper_md(item["md_path"])
            rule_limitations = strategy_class.extract(md_text)

            paper_result = {
                "paper_id": paper_id,
                "gold": gold_limitations,
                "rule": rule_limitations,
                "success": rule_limitations is not None
            }

            if rule_limitations:
                success_count += 1
            else:
                fail_count += 1

            results["papers"].append(paper_result)

        except Exception as e:
            fail_count += 1
            results["papers"].append({
                "paper_id": paper_id,
                "gold": gold_limitations,
                "rule": None,
                "success": False,
                "error": str(e)
            })

    results["summary"] = {
        "total": len(results["papers"]),
        "success": success_count,
        "fail": fail_count,
        "success_rate": success_count / len(results["papers"]) if results["papers"] else 0
    }

    return results


def save_result(results: Dict[str, Any], strategy_id: str):
    """保存测试结果"""
    output_dir = Path(__file__).parent / "results"
    output_dir.mkdir(exist_ok=True)

    output_file = output_dir / f"{strategy_id}_on_dev10.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"Saved results to: {output_file}")


def generate_report(all_results: Dict[str, Dict[str, Any]]):
    """生成对比分析报告"""
    analysis_dir = Path(__file__).parent / "analysis"
    analysis_dir.mkdir(exist_ok=True)

    lines = ["# Limitations字段策略对比分析\n"]
    lines.append(f"生成时间: {datetime.now().isoformat()}\n")

    lines.append("## 策略概览\n")
    lines.append("| 策略 | 成功率 | 成功数 | 失败数 |\n")
    lines.append("|------|--------|--------|--------|\n")

    for strategy_id, results in all_results.items():
        summary = results["summary"]
        lines.append(
            f"| {STRATEGY_NAMES[strategy_id]} | "
            f"{summary['success_rate']:.1%} | "
            f"{summary['success']} | "
            f"{summary['fail']} |\n"
        )

    lines.append("\n## 详细结果\n")
    for strategy_id, results in all_results.items():
        lines.append(f"\n### {STRATEGY_NAMES[strategy_id]}\n")
        lines.append(f"- 成功率: {results['summary']['success_rate']:.1%}\n")

        failures = [p for p in results["papers"] if not p["success"]]
        if failures:
            lines.append(f"\n**失败案例** ({len(failures)}个):\n")
            for f in failures:
                lines.append(f"- {f['paper_id']}: {f.get('error', 'No limitations found')}\n")

    comparison_file = analysis_dir / "comparison.md"
    with open(comparison_file, 'w', encoding='utf-8') as f:
        f.writelines(lines)

    print(f"Saved comparison report to: {comparison_file}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run limitations extraction tests")
    parser.add_argument("--strategy", choices=["v1", "v2", "v3", "v4", "v5", "vA", "vB", "vC", "vD", "vE", "vF", "vG", "vH", "vI", "vJ", "vK"], help="Test specific strategy")
    parser.add_argument("--compare-all", action="store_true", help="Compare all strategies")
    args = parser.parse_args()

    print("Loading gold data...")
    gold_data = load_gold_data("dev_10")
    print(f"Loaded {len(gold_data)} gold limitations")

    print("Loading manifest...")
    manifest = load_manifest("dev_10")
    print(f"Loaded {len(manifest)} papers")

    all_results = {}

    if args.strategy:
        print(f"\nTesting {STRATEGY_NAMES[args.strategy]}...")
        results = run_strategy_test(args.strategy, gold_data, manifest)
        save_result(results, args.strategy)
        print(f"\nSummary: {results['summary']['success_rate']:.1%} success rate")

    elif args.compare_all:
        print("\nComparing all strategies...")
        for strategy_id in STRATEGIES.keys():
            print(f"\nTesting {STRATEGY_NAMES[strategy_id]}...")
            results = run_strategy_test(strategy_id, gold_data, manifest)
            save_result(results, strategy_id)
            all_results[strategy_id] = results
            print(f"  Success rate: {results['summary']['success_rate']:.1%}")

        generate_report(all_results)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()