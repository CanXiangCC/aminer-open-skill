"""
limitations--策略A--条件式v1+v2

策略描述: v1+v2条件式fallback，优先v1（Limitations section），失败则v2（Conclusion）
Strategy: Conditional v1+v2, try v1 first, fallback to v2
"""

import re
import sys
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.shared.utils import extract_first_n_sentences, clean_markdown_text


class LimitationsRuleA:
    """局限性提取规则 - Limitations Extraction Rule - A (Conditional v1+v2)"""

    # v1: Limitations标题关键词
    V1_KEYWORDS = [
        "limitation",
        "limitations",
        "limitations and future work",
        "limitation and failure cases",
    ]

    # v2: Conclusion标题关键词
    V2_CONCLUSION_KEYWORDS = [
        "conclusion",
        "conclusions",
    ]

    # v2: Limitations内容关键词
    V2_LIMITATION_KEYWORDS = [
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
        提取局限性（v1优先，失败则v2）
        Extract limitations (v1 first, fallback to v2)

        Args:
            paper_md: 论文markdown文本
            max_sentences: 最大句子数

        Returns:
            Optional[str]: 提取的局限性
        """
        # === Layer 1: v1 - 直接Limitations section ===
        result = LimitationsRuleA._extract_v1(paper_md, max_sentences)
        if result:
            return result

        # === Layer 2: v2 - Conclusion中搜索 ===
        result = LimitationsRuleA._extract_v2(paper_md, max_sentences)
        if result:
            return result

        return None

    @staticmethod
    def _extract_v1(paper_md: str, max_sentences: int) -> Optional[str]:
        """v1: 直接Limitations section"""
        HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        matches = list(HEADER_RE.finditer(paper_md))

        for i, match in enumerate(matches):
            title = match.group(2).strip().lower()
            if any(kw in title for kw in LimitationsRuleA.V1_KEYWORDS):
                start = match.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(paper_md)
                content = paper_md[start:end].strip()
                cleaned = clean_markdown_text(content)
                sentences = extract_first_n_sentences(cleaned, n=max_sentences, method="regex")
                if sentences:
                    return " ".join(sentences)
        return None

    @staticmethod
    def _extract_v2(paper_md: str, max_sentences: int) -> Optional[str]:
        """v2: Conclusion中搜索limitation关键词"""
        HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        matches = list(HEADER_RE.finditer(paper_md))

        for i, match in enumerate(matches):
            title = match.group(2).strip().lower()
            if any(kw in title for kw in LimitationsRuleA.V2_CONCLUSION_KEYWORDS):
                start = match.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(paper_md)
                content = paper_md[start:end].strip()
                cleaned = clean_markdown_text(content)
                content_lower = cleaned.lower()

                if any(kw in content_lower for kw in LimitationsRuleA.V2_LIMITATION_KEYWORDS):
                    sentences = extract_first_n_sentences(cleaned, n=max_sentences, method="regex")
                    if sentences:
                        return " ".join(sentences)
        return None


if __name__ == "__main__":
    test_md = """
# Method
Our method uses...

# Limitations
Our approach has several limitations. First, it is computationally expensive.
    """

    result = LimitationsRuleA.extract(test_md)
    print(f"Extracted limitations: {result}")