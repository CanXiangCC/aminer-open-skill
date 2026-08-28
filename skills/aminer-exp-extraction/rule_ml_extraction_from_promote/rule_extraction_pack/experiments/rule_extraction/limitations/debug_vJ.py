"""
Debug why vJ still extracts TABLE content
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.limitations.test_runner import load_gold_data, load_manifest, load_paper_md
import experiments.rule_extraction.limitations.strategies.vJ_strict_filter as vJ_module

# 测试53e9a3fbb7602d9702d13e26 (extracted TABLE content)
gold_data = load_gold_data("dev_10")
manifest = load_manifest("dev_10")

paper_id = "53e9a3fbb7602d9702d13e26"
item = next((x for x in manifest if x["paper_id"] == paper_id), None)

md_text = load_paper_md(item["md_path"])
md_no_refs = vJ_module.LimitationsRuleJ._enhanced_remove_references(md_text)

# 测试过滤
test_sentences = [
    "TABLE 14 Summary of the limitations of our CSDN and its competitors.",
    "However, the last two images have nearly the same shape as the original image.",
]

print("=" * 80)
print(f"Testing {paper_id}")
print("=" * 80)

for sent in test_sentences:
    filtered = vJ_module.LimitationsRuleJ._should_filter(sent)
    print(f"  {sent[:60]}...")
    print(f"    -> {'FILTER' if filtered else 'KEEP'}")

# 实际提取
result = vJ_module.LimitationsRuleJ.extract(md_text)
print(f"\nActual vJ result:\n  {result[:150]}...")