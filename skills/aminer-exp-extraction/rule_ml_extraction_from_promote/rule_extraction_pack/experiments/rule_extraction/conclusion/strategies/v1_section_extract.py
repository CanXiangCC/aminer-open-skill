"""
conclusion--策略v1--section提取

策略描述: 直接提取Conclusion section内容，取前3句
Strategy: Extract Conclusion section content, take first 3 sentences
"""

import re
import sys
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.shared.utils import extract_first_n_sentences, clean_markdown_text


class ConclusionRuleV1:
    """结论提取规则 - Conclusion Extraction Rule - V1"""

    # Conclusion相关的section标题关键词
    SECTION_KEYWORDS = [
        "conclusion",
        "conclusions",
    ]

    @staticmethod
    def extract(paper_md: str, max_sentences: int = 3) -> Optional[str]:
        """
        提取结论
        Extract conclusion from markdown paper

        策略 Strategy:
        1. 查找Conclusion相关的section
        2. 提取该section的内容
        3. 清理Markdown格式
        4. 返回前max_sentences句

        Args:
            paper_md: 论文markdown文本 - Paper markdown text
            max_sentences: 最大句子数 - Maximum number of sentences

        Returns:
            Optional[str]: 提取的结论，未找到返回None - Extracted conclusion, None if not found
        """
        # 1. 查找Conclusion section - Find Conclusion section
        HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        matches = list(HEADER_RE.finditer(paper_md))

        if not matches:
            return None

        # 2. 匹配Conclusion section - Match Conclusion section
        for i, match in enumerate(matches):
            title = match.group(2).strip().lower()

            # 检查是否匹配关键词 - Check if matches keywords
            if any(keyword in title for keyword in ConclusionRuleV1.SECTION_KEYWORDS):
                # 提取section内容 - Extract section content
                start = match.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(paper_md)
                content = paper_md[start:end].strip()

                # 清理内容 - Clean content
                cleaned = clean_markdown_text(content)

                # 提取前N句 - Extract first N sentences
                sentences = extract_first_n_sentences(cleaned, n=max_sentences, method="regex")

                if sentences:
                    return " ".join(sentences)

        return None


if __name__ == "__main__":
    # 测试 - Test
    test_md = """
# Introduction
This is the introduction.

# Method
We propose a new method.

# VII. CONCLUSION
In this paper, we release the first large-scale FAS dataset. We propose a novel network. The results show significant improvement.

# References
[1] Some paper.
    """

    result = ConclusionRuleV1.extract(test_md)
    print(f"Extracted conclusion: {result}")