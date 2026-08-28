"""
limitations--策略v2--conclusion内搜索

策略描述: 在Conclusion section中搜索关键词
Strategy: Search for keywords in Conclusion section
"""

import re
import sys
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.shared.utils import extract_first_n_sentences, clean_markdown_text


class LimitationsRuleV2:
    """局限性提取规则 - Limitations Extraction Rule - V2"""

    # Conclusion section关键词
    CONCLUSION_KEYWORDS = [
        "conclusion",
        "conclusions",
    ]

    # Limitations内容关键词
    LIMITATION_KEYWORDS = [
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
        提取局限性（在Conclusion中搜索）
        Extract limitations (search in Conclusion section)

        策略 Strategy:
        1. 查找Conclusion section
        2. 在Conclusion内容中搜索limitation关键词
        3. 返回包含关键词的句子

        Args:
            paper_md: 论文markdown文本 - Paper markdown text
            max_sentences: 最大句子数 - Maximum number of sentences

        Returns:
            Optional[str]: 提取的局限性，未找到返回None - Extracted limitations, None if not found
        """
        # 1. 查找Conclusion section - Find Conclusion section
        HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        matches = list(HEADER_RE.finditer(paper_md))

        if not matches:
            return None

        # 2. 匹配Conclusion section - Match Conclusion section
        for i, match in enumerate(matches):
            title = match.group(2).strip().lower()

            if any(keyword in title for keyword in LimitationsRuleV2.CONCLUSION_KEYWORDS):
                # 提取section内容 - Extract section content
                start = match.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(paper_md)
                content = paper_md[start:end].strip()

                # 清理内容 - Clean content
                cleaned = clean_markdown_text(content)
                content_lower = cleaned.lower()

                # 检查是否包含limitation关键词 - Check if contains limitation keywords
                if any(kw in content_lower for kw in LimitationsRuleV2.LIMITATION_KEYWORDS):
                    # 提取前N句 - Extract first N sentences
                    sentences = extract_first_n_sentences(cleaned, n=max_sentences, method="regex")

                    if sentences:
                        return " ".join(sentences)

        return None


if __name__ == "__main__":
    # 测试 - Test
    test_md = """
# Method
Our method uses...

# Conclusion
Our results are promising. However, there are several limitations. Future work includes addressing scalability.
    """

    result = LimitationsRuleV2.extract(test_md)
    print(f"Extracted limitations: {result}")