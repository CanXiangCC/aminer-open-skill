"""
Check if failed cases contain "however"/"but" that were removed
"""

import json
from pathlib import Path

results_path = Path(__file__).parent / "results" / "vI_on_dev10.json"
with open(results_path, 'r', encoding='utf-8') as f:
    results = json.load(f)

print("=" * 80)
print("Analysis of vI Failed Cases")
print("=" * 80)

for paper in results["papers"]:
    gold = paper["gold"]
    paper_id = paper["paper_id"]

    # 检查Gold中是否包含被删除的信号词
    gold_lower = gold.lower()
    has_however = "however" in gold_lower
    has_but = "but" in gold_lower
    has_although = "although" in gold_lower
    has_despite = "despite" in gold_lower

    # 检查自指词
    has_our = "our" in gold_lower
    has_we = "we" in gold_lower
    has_this_work = "this work" in gold_lower

    status = "FAIL" if not paper["success"] else "OK"
    print(f"\n[{status}] {paper_id}")
    print(f"  Gold: {gold[:120]}...")
    print(f"  Signals: however={has_however}, but={has_but}, although={has_although}, despite={has_despite}")
    print(f"  Self-ref: our={has_our}, we={has_we}, this work={has_this_work}")