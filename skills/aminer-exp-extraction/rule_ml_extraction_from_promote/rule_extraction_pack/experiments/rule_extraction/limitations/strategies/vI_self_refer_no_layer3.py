"""
limitations--策略I--自指验证+vH删除误匹配信号词+取消Layer3

策略描述: vH基础上
  1. 添加自指验证（包含"our"/"we"/"this work"才返回）
  2. 删除误匹配信号词："however"/"but"/"benefits"/"future work"
  3. 取消Layer3，Layer1/2失败直接返回None（减少误判）

改进点:
- 自指验证确保是"本文的limitations"而非"其他方法的"
- 精简信号词列表，减少对比工作误匹配
- Layer1/2失败即None，宁可漏判不误判
Strategy: vH + self-reference validation + remove mismatched signals + cancel Layer3
"""

import re
import sys
from pathlib import Path
from typing import Optional

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.shared.utils import extract_first_n_sentences, clean_markdown_text


class LimitationsRuleI:
    """局限性提取规则 - Limitations Extraction Rule - I (vH enhanced)"""

    CONCLUSION_TITLES = [
        "conclusion",
        "conclusions",
        "discussion",
        "discussion and conclusion",
    ]

    # vH原始信号词，删除误匹配词
    _BASE_LIMITATION_SIGNALS = [
        "however",  # 已删除
        "but",  # 已删除
        "although",
        "despite",
        "nevertheless",
        "nonetheless",
        "on the other hand",
        "limitation",
        "limitations",
        "shortcoming",
        "constraint",
        "limited to",
        "fails to",
    ]

    # 精简后的信号词列表
    LIMITATION_SIGNALS = [s for s in _BASE_LIMITATION_SIGNALS if s not in ("however", "but")]

    # 自指关键词（确保是本文的limitations）
    SELF_REFER_KEYWORDS = [
        "our",
        "we",
        "this work",
        "our approach",
        "our method",
        "proposed",
    ]

    # 消极词（配合自指使用，排除"our benefits"等积极内容）
    NEGATIVE_KEYWORDS = [
        "limitation",
        "limitations",
        "shortcoming",
        "constraint",
        "fails to",
        "limited to",
        "cannot",
        "not",
        "however",  # 转折暗示问题
        "but",  # 转折暗示问题
    ]

    CITATION_PATTERNS = [
        r"[A-Z][a-z]+,\s+[A-Z][a-z]+\s+\w+\s+\d{4}",
        r"\bet\.\s+al\.",
        r"\b(?:in|at)\s+(?:ICRA|CVPR|NeurIPS|ICML|AAAI|ECCV|IJCAI)",
        r"\bpp\.\s+\d+(?:-\d+)?",
        r"\[\d+(?:-\d+)?\]",
        r"\b(?:doi\.org|doi:)",
    ]

    @staticmethod
    def _enhanced_remove_references(paper_md: str) -> str:
        """增强的引用删除：先尝试标准References，失败则检测混杂引用"""
        cleaned = LimitationsRuleI._remove_standard_references(paper_md)
        if cleaned != paper_md:
            return cleaned
        return LimitationsRuleI._remove_embedded_citations(paper_md)

    @staticmethod
    def _remove_standard_references(paper_md: str) -> str:
        """删除标准References section"""
        patterns = [
            r"^#{1,3}\s*(?:References|Bibliography|Works Cited)\s*$",
            r"^\s*(?:References|Bibliography)\s*$",
        ]

        for pattern in patterns:
            match = re.search(pattern, paper_md, re.IGNORECASE | re.MULTILINE)
            if match:
                return paper_md[:match.start()].rstrip()

        return paper_md

    @staticmethod
    def _remove_embedded_citations(paper_md: str) -> str:
        """删除混杂引用（从论文末尾检测）"""
        for pattern in LimitationsRuleI.CITATION_PATTERNS:
            matches = list(re.finditer(pattern, paper_md, re.IGNORECASE))
            if matches:
                last_match = matches[-1]
                citation_region = paper_md[last_match.start():]

                citation_density = (
                    citation_region.count("et al") +
                    citation_region.count("pp.") +
                    citation_region.count("IEEE") +
                    citation_region.count("ICRA") +
                    citation_region.count("CVPR") +
                    citation_region.count("NeurIPS") +
                    citation_region.count("[1]") +
                    citation_region.count("doi")
                )

                if citation_density >= 3:
                    return paper_md[:last_match.start()].rstrip()

        return paper_md

    @staticmethod
    def extract(paper_md: str, max_sentences: int = 2) -> Optional[str]:
        """
        提取局限性（vI: vH + 自指验证 + 精简信号词 + 取消Layer3）

        Args:
            paper_md: 论文markdown文本
            max_sentences: 最大句子数

        Returns:
            Optional[str]: 提取的局限性
        """
        md_no_refs = LimitationsRuleI._enhanced_remove_references(paper_md)

        # === Layer 1: Conclusion中找信号句（带自指验证）===
        result = LimitationsRuleI._extract_from_conclusion(md_no_refs, max_sentences)
        if result:
            return result

        # === Layer 2: 全文后20%找信号句（带自指验证）===
        result = LimitationsRuleI._extract_from_last_20_percent(md_no_refs, max_sentences)
        if result:
            return result

        # === Layer 3取消，直接返回None ===
        # 宁可漏判不误判，vH的Layer3容易提取到不相关内容
        return None

    @staticmethod
    def _extract_from_conclusion(paper_md: str, max_sentences: int) -> Optional[str]:
        """在Conclusion section中找局限性信号句（带自指验证）"""
        HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        matches = list(HEADER_RE.finditer(paper_md))

        for i, match in enumerate(matches):
            title = match.group(2).strip().lower()

            if any(kw in title for kw in LimitationsRuleI.CONCLUSION_TITLES):
                start = match.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(paper_md)
                content = paper_md[start:end].strip()
                cleaned = clean_markdown_text(content)

                return LimitationsRuleI._find_signal_sentence(cleaned, max_sentences)

        return None

    @staticmethod
    def _extract_from_last_20_percent(paper_md: str, max_sentences: int) -> Optional[str]:
        """在全文后20%找局限性信号句（带自指验证）"""
        start_pos = int(len(paper_md) * 0.8)
        last_20 = paper_md[start_pos:]

        cleaned = clean_markdown_text(last_20)
        return LimitationsRuleI._find_signal_sentence(cleaned, max_sentences)

    @staticmethod
    def _find_signal_sentence(text: str, max_sentences: int) -> Optional[str]:
        """
        在文本中找局限性信号句（带自指验证）

        新增验证：
        1. 必须包含自指关键词（"our"/"we"/"this work"）
        2. 建议包含消极词（"limitation"/"cannot"等）避免"our benefits"误匹配
        """
        all_sentences = extract_first_n_sentences(text, n=len(text), method="regex")

        for signal in LimitationsRuleI.LIMITATION_SIGNALS:
            for j in range(len(all_sentences) - 1, -1, -1):
                sent_lower = all_sentences[j].lower()

                if signal in sent_lower:
                    # === 新增：自指验证 ===
                    has_self_refer = any(kw in sent_lower for kw in LimitationsRuleI.SELF_REFER_KEYWORDS)
                    if not has_self_refer:
                        continue  # 不是本文的limitations，跳过

                    # 可选：消极词验证（避免"our benefits"等）
                    has_negative = any(kw in sent_lower for kw in LimitationsRuleI.NEGATIVE_KEYWORDS)

                    # 如果只有自指没有消极词，需要更谨慎
                    # 但保留"however"/"but"作为转折信号
                    if not has_negative and signal not in ("however", "but"):
                        continue  # 可能是积极内容，跳过

                    # 取信号句+后1句
                    end_idx = min(len(all_sentences), j + 2)
                    selected = all_sentences[j:end_idx]
                    if selected:
                        return " ".join(selected[:max_sentences])

        return None


if __name__ == "__main__":
    # 测试: 自指验证
    test_md_our = """
# Conclusion
Our method achieves SOTA results on ImageNet. However, our approach is computationally expensive.
    """

    test_md_other = """
# Conclusion
The baseline method works well. However, it has some limitations on edge cases.
    """

    test_md_benefits = """
# Conclusion
Our approach provides several benefits. We demonstrate improved performance on ImageNet.
    """

    print("Testing 'our' limitations:")
    result = LimitationsRuleI.extract(test_md_our)
    print(f"  {result}")

    print("\nTesting 'other method' limitations (should be None):")
    result = LimitationsRuleI.extract(test_md_other)
    print(f"  {result}")

    print("\nTesting 'our benefits' (should be None):")
    result = LimitationsRuleI.extract(test_md_benefits)
    print(f"  {result}")