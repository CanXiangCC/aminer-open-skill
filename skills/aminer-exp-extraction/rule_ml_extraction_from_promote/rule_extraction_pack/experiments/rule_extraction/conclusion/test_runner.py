"""
Conclusion字段测试运行器 - Conclusion Field Test Runner

统一运行所有策略在dev_10上的测试
Unified test runner for all strategies on dev_10
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# 导入策略（使用文件名，不是类名）
# Import strategies using file names, not class names
import experiments.rule_extraction.conclusion.strategies.v1_section_extract as v1_module
import experiments.rule_extraction.conclusion.strategies.v2_title_match as v2_module
import experiments.rule_extraction.conclusion.strategies.v3_keyword_enhanced as v3_module
import experiments.rule_extraction.conclusion.strategies.v5_layered as v5_module

# 策略映射
STRATEGIES = {
    "v1": v1_module.ConclusionRuleV1,
    "v2": v2_module.ConclusionRuleV2,
    "v3": v3_module.ConclusionRuleV3,
    "v5": v5_module.ConclusionRuleV5,
}

STRATEGY_NAMES = {
    "v1": "conclusion--策略v1--section提取",
    "v2": "conclusion--策略v2--标题匹配",
    "v3": "conclusion--策略v3--关键词增强",
    "v5": "conclusion--策略v5--三层分层",
}


def load_gold_data(batch: str = "dev_10") -> Dict[str, str]:
    """
    加载Gold标准的conclusion数据
    Load gold standard conclusion data
    """
    gold_dir = project_root / "data" / "gold" / batch / "full_text_glm5_2"
    gold_data = {}

    for json_file in gold_dir.glob("*.json"):
        paper_id = json_file.stem
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 可能是数组或单个对象 - Could be array or single object
                experiments = data if isinstance(data, list) else [data]
                for exp in experiments:
                    conclusion = exp.get("conclusion")
                    if conclusion:
                        gold_data[paper_id] = conclusion
                        break
        except Exception as e:
            print(f"Error loading {json_file}: {e}")

    return gold_data


def load_manifest(batch: str = "dev_10") -> List[Dict[str, Any]]:
    """
    加载manifest文件
    Load manifest file
    """
    manifest_path = project_root / "data" / "fixtures" / batch / "manifest.json"
    with open(manifest_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_paper_md(md_path: str) -> str:
    """
    加载论文markdown
    Load paper markdown
    """
    full_path = project_root / md_path
    with open(full_path, 'r', encoding='utf-8') as f:
        return f.read()


def run_strategy_test(strategy_id: str, gold_data: Dict[str, str], manifest: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    运行单个策略测试
    Run single strategy test
    """
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
        gold_conclusion = gold_data.get(paper_id)

        if gold_conclusion is None:
            # 无gold数据，跳过 - Skip if no gold data
            continue

        try:
            # 加载论文 - Load paper
            md_text = load_paper_md(item["md_path"])

            # 运行策略 - Run strategy
            rule_conclusion = strategy_class.extract(md_text)

            # 记录结果 - Record result
            paper_result = {
                "paper_id": paper_id,
                "gold": gold_conclusion,
                "rule": rule_conclusion,
                "success": rule_conclusion is not None
            }

            if rule_conclusion:
                success_count += 1
            else:
                fail_count += 1

            results["papers"].append(paper_result)

        except Exception as e:
            fail_count += 1
            results["papers"].append({
                "paper_id": paper_id,
                "gold": gold_conclusion,
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
    """
    保存测试结果
    Save test results
    """
    output_dir = Path(__file__).parent / "results"
    output_dir.mkdir(exist_ok=True)

    output_file = output_dir / f"{strategy_id}_on_dev10.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"Saved results to: {output_file}")


def generate_report(all_results: Dict[str, Dict[str, Any]]):
    """
    生成对比分析报告
    Generate comparison report
    """
    analysis_dir = Path(__file__).parent / "analysis"
    analysis_dir.mkdir(exist_ok=True)

    lines = ["# Conclusion字段策略对比分析\n"]
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

    # 详细结果
    lines.append("\n## 详细结果\n")
    for strategy_id, results in all_results.items():
        lines.append(f"\n### {STRATEGY_NAMES[strategy_id]}\n")
        lines.append(f"- 成功率: {results['summary']['success_rate']:.1%}\n")

        # 失败案例
        failures = [p for p in results["papers"] if not p["success"]]
        if failures:
            lines.append(f"\n**失败案例** ({len(failures)}个):\n")
            for f in failures:
                lines.append(f"- {f['paper_id']}: {f.get('error', 'No conclusion section')}\n")

    # 写入文件 - Write to file
    comparison_file = analysis_dir / "comparison.md"
    with open(comparison_file, 'w', encoding='utf-8') as f:
        f.writelines(lines)

    print(f"Saved comparison report to: {comparison_file}")


def main():
    """
    主函数
    Main function
    """
    import argparse

    parser = argparse.ArgumentParser(description="Run conclusion extraction tests")
    parser.add_argument("--strategy", choices=["v1", "v2", "v3", "v5"], help="Test specific strategy")
    parser.add_argument("--compare-all", action="store_true", help="Compare all strategies")
    args = parser.parse_args()

    # 加载数据 - Load data
    print("Loading gold data...")
    gold_data = load_gold_data("dev_10")
    print(f"Loaded {len(gold_data)} gold conclusions")

    print("Loading manifest...")
    manifest = load_manifest("dev_10")
    print(f"Loaded {len(manifest)} papers")

    all_results = {}

    if args.strategy:
        # 测试单个策略 - Test single strategy
        print(f"\nTesting {STRATEGY_NAMES[args.strategy]}...")
        results = run_strategy_test(args.strategy, gold_data, manifest)
        save_result(results, args.strategy)
        print(f"\nSummary: {results['summary']['success_rate']:.1%} success rate")

    elif args.compare_all:
        # 对比所有策略 - Compare all strategies
        print("\nComparing all strategies...")
        for strategy_id in STRATEGIES.keys():
            print(f"\nTesting {STRATEGY_NAMES[strategy_id]}...")
            results = run_strategy_test(strategy_id, gold_data, manifest)
            save_result(results, strategy_id)
            all_results[strategy_id] = results
            print(f"  Success rate: {results['summary']['success_rate']:.1%}")

        # 生成对比报告 - Generate comparison report
        generate_report(all_results)

    else:
        # 默认测试所有策略 - Default: test all strategies
        parser.print_help()


if __name__ == "__main__":
    main()