"""
limitations--策略B--增强v1 + Conclusion搜索

策略描述: v1增强header检测 + Conclusion中搜索（后N句）
Strategy: Enhanced v1 + Conclusion search (last N sentences)
"""

import re
import sys
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.shared.utils import extract_first_n_sentences, clean_markdown_text


class LimitationsRuleB:
    """局限性提取规则 - Limitations Extraction Rule - B (Enhanced v1 + Conclusion)"""

    # 统一header检测（支持Markdown/罗马数字/数字）
    _HEADER_RE = re.compile(
        r"^" + r"(#{1,6}\s+.+)|" +
        r"([IVXLCDM]+\s*[.)]\s+.+)|" +
        r"(\d+(?:\.\d+)*\s+[.)]\s+.+)|" +
        r"^[A-Z\s]{10,}$",
        re.MULTILINE
    )

    # Limitations标题关键词
    LIMITATION_TITLES = [
        "limitation",
        "limitations",
        "limitations and future work",
        "limitation and failure cases",
    ]

    # Conclusion标题关键词
    CONCLUSION_TITLES = [
        "conclusion",
        "conclusions",
        "conclusion and future work",
    ]

    # Conclusion中limitations关键词
    CONCLUSION_LIMITATION_KW = [
        "limitation",
        "limitations",
        "however",
        "but",
        "although",
        "shortcoming",
        "weakness",
        "constraint",
        "challenge",
        "future work",
    ]

    @staticmethod
    def _extract_header_title(header_text: str) -> str:
        """从header文本中提取标题（移除前缀）"""
        header_text = header_text.strip()

        if header_text.startswith('#'):
            return re.sub(r'^#{1,6}\s+', '', header_text).strip()

        roman_match = re.match(r'^[IVXLCDM]+\s*[.)]\s*', header_text, re.IGNORECASE)
        if roman_match:
            return header_text[roman_match.end():].strip()

        num_match = re.match(r'^\d+(?:\.\d+)*\s+[.)]\s*', header_text)
        if num_match:
            return header_text[num_match.end():].strip()

        return header_text

    @staticmethod
    def extract(paper_md: str, max_sentences: int = 2) -> Optional[str]:
        """
        提取局限性（增强v1 + Conclusion搜索）

        Args:
            paper_md: 论文markdown文本
            max_sentences: 最大句子数

        Returns:
            Optional[str]: 提取的局限性
        """
        matches = list(LimitationsRuleB._HEADER_RE.finditer(paper_md))

        # === Layer 1: 增强v1 ===
        for i, match in enumerate(matches):
            header_text = match.group().strip()
            title = LimitationsRuleB._extract_header_title(header_text).lower()

            if any(kw in title for kw in LimitationsRuleB.LIMITATION_TITLES):
                start = match.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(paper_md)
                content = paper_md[start:end].strip()
                cleaned = clean_markdown_text(content)
                sentences = extract_first_n_sentences(cleaned, n=max_sentences, method="regex")
                if sentences:
                    return " ".join(sentences)

        # === Layer 2: Conclusion中搜索（后N句）===
        for i, match in enumerate(matches):
            header_text = match.group().strip()
            title = LimitationsRuleB._extract_header_title(header_text).lower()

            if any(kw in title for kw in LimitationsRuleB.CONCLUSION_TITLES):
                start = match.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(paper_md)
                content = paper_md[start:end].strip()
                cleaned = clean_markdown_text(content)
                content_lower = cleaned.lower()

                # 检查是否包含limitations关键词
                if any(kw in content_lower for kw in LimitationsRuleB.CONCLUSION_LIMITATION_KW):
                    # 取后N句（因为limitations通常在结论末尾）
                    all_sentences = extract_first_n_sentences(cleaned, n=len(cleaned), method="regex")
                    if len(all_sentences) >= max_sentences:
                        return " ".join(all_sentences[-max_sentences:])
                    elif all_sentences:
                        return " ".join(all_sentences)

        return None


if __name__ == "__main__":
    test_md = """
# Method
Our method uses...

# Conclusion
Our results are promising. However, our approach has limitations regarding scalability.
    """

    result = LimitationsRuleB.extract(test_md)
    print(f"Extracted limitations: {result}")