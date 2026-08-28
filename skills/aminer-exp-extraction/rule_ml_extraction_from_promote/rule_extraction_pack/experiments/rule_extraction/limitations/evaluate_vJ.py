"""
Evaluate vJ quality vs vH
"""

import json
from pathlib import Path

vH_path = Path(__file__).parent / "results" / "vH_on_dev10.json"
vJ_path = Path(__file__).parent / "results" / "vJ_on_dev10.json"

with open(vH_path, 'r', encoding='utf-8') as f:
    vH_results = json.load(f)
with open(vJ_path, 'r', encoding='utf-8') as f:
    vJ_results = json.load(f)

vH_map = {p["paper_id"]: p for p in vH_results["papers"]}
vJ_map = {p["paper_id"]: p for p in vJ_results["papers"]}

print("=" * 80)
print("vH vs vJ Quality Comparison")
print("=" * 80)

# 简单质量评估：检查关键词
def quality_check(rule: str) -> str:
    if not rule:
        return "N/A"
    rule_lower = rule.lower()

    # 明确误匹配
    if "table" in rule_lower or "fig" in rule_lower:
        return "POOR - table/fig"
    if "future" in rule_lower and "research" in rule_lower:
        return "POOR - future work"
    if "we propose" in rule_lower or "in addition, we propose" in rule_lower:
        return "POOR - method intro"
    if "in our work, we focus" in rule_lower:
        return "POOR - work intro"

    # 可能正确
    if "limitation" in rule_lower:
        return "GOOD - explicit"
    if "however" in rule_lower and "our" in rule_lower:
        return "GOOD - however+our"
    if "but" in rule_lower and "our" in rule_lower:
        return "GOOD - but+our"
    if "fails to" in rule_lower:
        return "GOOD - fails to"
    if "despite" in rule_lower:
        return "MAYBE - despite"

    return "UNCLEAR"

for paper in vJ_results["papers"]:
    paper_id = paper["paper_id"]
    gold = paper["gold"]
    vH_rule = vH_map[paper_id]["rule"]
    vJ_rule = paper["rule"]

    vH_quality = quality_check(vH_rule)
    vJ_quality = quality_check(vJ_rule)

    print(f"\n### {paper_id}")
    print(f"Gold:  {gold[:80]}...")
    print(f"vH:    {vH_rule[:60]}... [{vH_quality}]")
    print(f"vJ:    {vJ_rule[:60]}... [{vJ_quality}]")