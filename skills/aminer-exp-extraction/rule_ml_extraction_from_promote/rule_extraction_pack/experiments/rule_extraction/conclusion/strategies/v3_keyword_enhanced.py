"""
conclusion--策略v3--关键词增强

策略描述: Section + 关键词双重验证
Strategy: Section + keyword double validation
"""

import re
import sys
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.shared.utils import extract_first_n_sentences, clean_markdown_text


class ConclusionRuleV3:
    """结论提取规则 - Conclusion Extraction Rule - V3"""

    # Section标题模式（复用v2）
    SECTION_PATTERNS = [
        r"^conclusions?$",
        r"^[ivxlcdm]+\.\s+conclusions?$",
        r"^[ivxlcdm]+\)\s+conclusions?$",
        r"^\d+\.\s+conclusions?$",
        r"^section\s+\d+\.?\d*\s*:?\s*conclusions?$",
        r"conclusion\s+and\s+future\s+work",
    ]

    # 内容关键词（验证提取内容确实是结论）
    CONTENT_KEYWORDS = [
        "conclusion",
        "propose",
        "achieve",
        "result",
        "performance",
        "improve",
        "outperform",
        "demonstrate",
        "show",
        "effective",
        "future work",
    ]

    @staticmethod
    def extract(paper_md: str, max_sentences: int = 3) -> Optional[str]:
        """
        提取结论（关键词增强）
        Extract conclusion (keyword enhanced)

        策略 Strategy:
        1. 使用多种模式匹配Conclusion标题
        2. 验证内容包含结论相关关键词
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
            for pattern in ConclusionRuleV3.SECTION_PATTERNS:
                if re.search(pattern, title_lower, re.IGNORECASE):
                    # 提取section内容 - Extract section content
                    start = match.end()
                    end = matches[i + 1].start() if i + 1 < len(matches) else len(paper_md)
                    content = paper_md[start:end].strip()

                    # 清理内容 - Clean content
                    cleaned = clean_markdown_text(content)

                    # 关键词验证 - Keyword validation
                    content_lower = cleaned.lower()
                    if not any(keyword in content_lower for keyword in ConclusionRuleV3.CONTENT_KEYWORDS):
                        # 内容不包含关键词，跳过 - Skip if no keywords in content
                        continue

                    # 提取前N句 - Extract first N sentences
                    sentences = extract_first_n_sentences(cleaned, n=max_sentences, method="regex")

                    if sentences:
                        return " ".join(sentences)

        return None


if __name__ == "__main__":
    # 测试用例 - Test cases
    test_cases = [
        ("# CONCLUSION\nOur method achieves SOTA results. The performance is improved.", "With keywords"),
        ("# CONCLUSION\nThis is a section about something else.\nNo results here.", "Without keywords"),
        ("# VII. CONCLUSION\nWe demonstrate that our approach is effective. Future work includes.", "Roman + keywords"),
    ]

    print("=== Conclusion Rule V3 Tests ===")
    for md, desc in test_cases:
        result = ConclusionRuleV3.extract(md)
        if result:
            print(f"PASS {desc}: {result[:50]}...")
        else:
            print(f"FAIL {desc}: None")