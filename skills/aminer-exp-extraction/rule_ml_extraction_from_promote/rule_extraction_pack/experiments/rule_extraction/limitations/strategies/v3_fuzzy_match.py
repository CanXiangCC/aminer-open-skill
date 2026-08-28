"""
limitations--策略v3--全文模糊匹配

策略描述: 全文搜索，返回最相关段落
Strategy: Full text search, return most relevant paragraph
"""

import re
import sys
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.shared.utils import extract_first_n_sentences, clean_markdown_text


class LimitationsRuleV3:
    """局限性提取规则 - Limitations Extraction Rule - V3"""

    # Limitations内容关键词
    KEYWORDS = [
        "limitation",
        "limitations",
        "shortcoming",
        "shortcomings",
        "weakness",
        "weaknesses",
        "drawback",
        "drawbacks",
        "constraint",
        "constraints",
        "challenge",
        "challenges",
        "future work",
        "future direction",
    ]

    @staticmethod
    def extract(paper_md: str, max_sentences: int = 2) -> Optional[str]:
        """
        提取局限性（全文模糊匹配）
        Extract limitations (full text fuzzy match)

        策略 Strategy:
        1. 移除section headers，获得纯文本
        2. 按段落分割
        3. 找到包含最多limitation关键词的段落
        4. 返回该段落的前N句

        Args:
            paper_md: 论文markdown文本 - Paper markdown text
            max_sentences: 最大句子数 - Maximum number of sentences

        Returns:
            Optional[str]: 提取的局限性，未找到返回None - Extracted limitations, None if not found
        """
        # 1. 移除headers - Remove headers
        HEADER_RE = re.compile(r"^#{1,6}\s+.+$", re.MULTILINE)
        clean_md = HEADER_RE.sub("", paper_md)

        # 2. 按段落分割 - Split by paragraphs
        paragraphs = re.split(r"\n{2,}", clean_md.strip())

        # 3. 找到最相关的段落 - Find most relevant paragraph
        best_paragraph = None
        best_score = 0

        for para in paragraphs:
            para_lower = para.lower()
            # 计算关键词匹配分数 - Calculate keyword match score
            score = sum(1 for kw in LimitationsRuleV3.KEYWORDS if kw in para_lower)

            if score > best_score:
                best_score = score
                best_paragraph = para

        # 4. 如果找到相关段落，返回 - Return if found
        if best_paragraph and best_score >= 1:
            cleaned = clean_markdown_text(best_paragraph)
            sentences = extract_first_n_sentences(cleaned, n=max_sentences, method="regex")

            if sentences:
                return " ".join(sentences)

        return None


if __name__ == "__main__":
    # 测试 - Test
    test_md = """
# Introduction
This paper proposes...

# Results
The method achieves good performance.

# Discussion
However, there are several limitations to our approach. First, it requires large datasets. Second, the computational cost is high.

# Conclusion
Future work will address these issues.
    """

    result = LimitationsRuleV3.extract(test_md)
    print(f"Extracted limitations: {result}")