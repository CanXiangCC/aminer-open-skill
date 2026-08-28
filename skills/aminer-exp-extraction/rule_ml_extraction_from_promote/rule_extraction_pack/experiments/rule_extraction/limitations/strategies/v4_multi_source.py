"""
limitations--策略v4--多源融合

策略描述: 合并多个来源的信息
Strategy: Combine information from multiple sources
"""

import sys
from pathlib import Path
from typing import Optional, List

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.shared.utils import extract_first_n_sentences, clean_markdown_text

import experiments.rule_extraction.limitations.strategies.v1_section_extract as v1_module
import experiments.rule_extraction.limitations.strategies.v2_conclusion_search as v2_module
import experiments.rule_extraction.limitations.strategies.v3_fuzzy_match as v3_module


class LimitationsRuleV4:
    """局限性提取规则 - Limitations Extraction Rule - V4"""

    @staticmethod
    def extract(paper_md: str, max_sentences: int = 2) -> Optional[str]:
        """
        提取局限性（多源融合）
        Extract limitations (multi-source fusion)

        策略 Strategy:
        1. 依次尝试v1, v2, v3
        2. 取第一个成功的结果
        3. 合并多个来源（如有需要）

        Args:
            paper_md: 论文markdown文本 - Paper markdown text
            max_sentences: 最大句子数 - Maximum number of sentences

        Returns:
            Optional[str]: 提取的局限性，未找到返回None - Extracted limitations, None if not found
        """
        # 依次尝试各策略 - Try each strategy in order
        for strategy in [v1_module.LimitationsRuleV1,
                         v2_module.LimitationsRuleV2,
                         v3_module.LimitationsRuleV3]:
            result = strategy.extract(paper_md, max_sentences=max_sentences)
            if result:
                return result

        return None


if __name__ == "__main__":
    # 测试 - Test
    test_md_v1 = """
# Limitations
Our approach has limitations. It is slow.
    """

    test_md_v2 = """
# Conclusion
Our method is good. However, it has some limitations.
    """

    test_md_v3 = """
# Discussion
There are limitations: cost and speed.
    """

    print("Testing v1 input:")
    result = LimitationsRuleV4.extract(test_md_v1)
    print(f"  {result}")

    print("Testing v2 input:")
    result = LimitationsRuleV4.extract(test_md_v2)
    print(f"  {result}")

    print("Testing v3 input:")
    result = LimitationsRuleV4.extract(test_md_v3)
    print(f"  {result}")