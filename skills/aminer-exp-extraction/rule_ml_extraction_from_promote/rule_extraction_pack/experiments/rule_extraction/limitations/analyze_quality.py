"""
Analyze vH results for vI failed cases - check quality
"""

import json
from pathlib import Path

vH_path = Path(__file__).parent / "results" / "vH_on_dev10.json"
vI_path = Path(__file__).parent / "results" / "vI_on_dev10.json"

with open(vH_path, 'r', encoding='utf-8') as f:
    vH_results = json.load(f)
with open(vI_path, 'r', encoding='utf-8') as f:
    vI_results = json.load(f)

vH_map = {p["paper_id"]: p for p in vH_results["papers"]}

print("=" * 80)
print("vH vs vI: Quality Analysis for vI Failed Cases")
print("=" * 80)

# 获取vI失败的paper
vI_failed = [p for p in vI_results["papers"] if not p["success"]]

for paper in vI_failed:
    paper_id = paper["paper_id"]
    gold = paper["gold"]
    vH = vH_map[paper_id]["rule"] if paper_id in vH_map else None

    print(f"\n### {paper_id}")
    print(f"Gold: {gold}")
    print(f"vH:   {vH}")

    # 人工评估vH质量
    print(f"Quality: [需要人工评估]")