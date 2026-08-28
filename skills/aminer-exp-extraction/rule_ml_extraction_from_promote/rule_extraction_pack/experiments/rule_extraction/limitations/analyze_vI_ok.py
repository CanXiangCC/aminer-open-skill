"""
Analyze vI successful cases - check if they are actually correct
"""

import json
from pathlib import Path

vI_path = Path(__file__).parent / "results" / "vI_on_dev10.json"

with open(vI_path, 'r', encoding='utf-8') as f:
    vI_results = json.load(f)

vI_ok = [p for p in vI_results["papers"] if p["success"]]

print("=" * 80)
print("vI Successful Cases - Quality Analysis")
print("=" * 80)

for paper in vI_ok:
    paper_id = paper["paper_id"]
    gold = paper["gold"]
    rule = paper["rule"]

    print(f"\n### {paper_id}")
    print(f"Gold: {gold[:120]}...")
    print(f"vI:   {rule[:120]}...")

    # 质量评估
    if "TABLE" in rule:
        print(f"Quality: POOR - table caption")
    elif "FUTURE" in rule.upper():
        print(f"Quality: POOR - future work, not limitation")
    elif "CONCLUSION" in rule.upper():
        print(f"Quality: POOR - conclusion intro, not limitation")
    else:
        print(f"Quality: NEED REVIEW")