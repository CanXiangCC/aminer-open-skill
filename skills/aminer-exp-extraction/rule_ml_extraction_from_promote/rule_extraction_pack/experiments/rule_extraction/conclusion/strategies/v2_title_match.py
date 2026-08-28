"""
conclusion--策略v2--标题匹配

策略描述: 匹配多种Conclusion变体标题（含罗马数字、编号等）
Strategy: Match multiple Conclusion title variations (including Roman numerals, numbers, etc.)
"""

import re
import sys
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.shared.utils import extract_first_n_sentences, clean_markdown_text


class ConclusionRuleV2:
    """结论提取规则 - Conclusion Extraction Rule - V2"""

    # Conclusion相关的section标题模式（更灵活）
    SECTION_PATTERNS = [
        r"^conclusions?$",  # Conclusion / Conclusions
        r"^[ivxlcdm]+\.\s+conclusions?$",  # VII. Conclusion / VIII. Conclusions
        r"^[ivxlcdm]+\)\s+conclusions?$",  # VII) Conclusion
        r"^\d+\.\s+conclusions?$",  # 7. Conclusion / 8. Conclusions
        r"^section\s+\d+\.?\d*\s*:?\s*conclusions?$",  # Section 7: Conclusion
        r"conclusion\s+and\s+future\s+work",  # Conclusion and Future Work
    ]

    @staticmethod
    def extract(paper_md: str, max_sentences: int = 3) -> Optional[str]:
        """
        提取结论（增强版标题匹配）
        Extract conclusion (enhanced title matching)

        策略 Strategy:
        1. 使用多种模式匹配Conclusion标题
        2. 支持罗马数字、数字、Section编号等变体
        3. 清理Markdown格式
        4. 返回前max_sentences句

        Args:
            paper_md: 论文markdown文本 - Paper markdown text
            max_sentences: 最大句子数 - Maximum number of sentences

        Returns:
            Optional[str]: 提取的结论，未找到返回None - Extracted conclusion, None if not found
        """
        # 1. 查找所有headers - Find all headers
        HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        matches = list(HEADER_RE.finditer(paper_md))

        if not matches:
            return None

        # 2. 匹配Conclusion section - Match Conclusion section
        for i, match in enumerate(matches):
            title = match.group(2).strip()
            title_lower = title.lower()

            # 检查是否匹配任一模式 - Check if matches any pattern
            for pattern in ConclusionRuleV2.SECTION_PATTERNS:
                if re.search(pattern, title_lower, re.IGNORECASE):
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
    # 测试用例 - Test cases
    test_cases = [
        ("# VII. CONCLUSION\nIn this paper...", "Roman numeral VII"),
        ("# 8. Conclusions\nOur method...", "Number 8"),
        ("# Section 7.2: Conclusion\nThe results...", "Section 7.2"),
        ("# Conclusion and Future Work\nWe will...", "With Future Work"),
    ]

    print("=== Conclusion Rule V2 Tests ===")
    for md, desc in test_cases:
        result = ConclusionRuleV2.extract(md)
        status = "PASS" if result else "FAIL"
        print(f"{status} {desc}: {result[:40] if result else 'None'}...")