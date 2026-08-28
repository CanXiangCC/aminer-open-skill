"""
Debug script to understand why vI has lower success rate than vH
"""

import json
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.limitations.test_runner import load_gold_data, load_manifest, load_paper_md
import experiments.rule_extraction.limitations.strategies.vH_enhanced_refs as vH_module
import experiments.rule_extraction.limitations.strategies.vI_self_refer_no_layer3 as vI_module

gold_data = load_gold_data("dev_10")
manifest = load_manifest("dev_10")

print("=" * 80)
print("vI vs vH Comparison (dev_10)")
print("=" * 80)

for paper_id, gold_limitations in gold_data.items():
    item = next((x for x in manifest if x["paper_id"] == paper_id), None)
    if not item:
        continue

    md_text = load_paper_md(item["md_path"])

    vH_result = vH_module.LimitationsRuleH.extract(md_text)
    vI_result = vI_module.LimitationsRuleI.extract(md_text)

    print(f"\n### Paper: {paper_id}")
    print(f"Gold: {gold_limitations[:100]}..." if len(gold_limitations) > 100 else f"Gold: {gold_limitations}")
    print(f"vH: {vH_result[:100] if vH_result else 'None'}...")
    print(f"vI: {vI_result[:100] if vI_result else 'None'}...")
    print(f"Status: {'OK vI matched' if vI_result else 'FAIL vI failed'}")