"""
limitations--策略H--增强引用删除（vG + 混杂引用检测）
"""

import re
import sys
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.shared.utils import extract_first_n_sentences, clean_markdown_text


class LimitationsRuleH:
    """局限性提取规则 - Limitations Extraction Rule - H (Enhanced refs removal)"""

    CONCLUSION_TITLES = [
        "conclusion",
        "conclusions",
        "discussion",
        "discussion and conclusion",
    ]

    LIMITATION_SIGNALS = [
        "however",
        "but",
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
        cleaned = LimitationsRuleH._remove_standard_references(paper_md)
        if cleaned != paper_md:
            return cleaned
        return LimitationsRuleH._remove_embedded_citations(paper_md)

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
        for pattern in LimitationsRuleH.CITATION_PATTERNS:
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
        """提取局限性"""
        md_no_refs = LimitationsRuleH._enhanced_remove_references(paper_md)

        result = LimitationsRuleH._extract_from_conclusion(md_no_refs, max_sentences)
        if result:
            return result

        result = LimitationsRuleH._extract_from_last_20_percent(md_no_refs, max_sentences)
        if result:
            return result

        return None

    @staticmethod
    def _extract_from_conclusion(paper_md: str, max_sentences: int) -> Optional[str]:
        """在Conclusion section中找局限性信号句"""
        HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        matches = list(HEADER_RE.finditer(paper_md))

        for i, match in enumerate(matches):
            title = match.group(2).strip().lower()

            if any(kw in title for kw in LimitationsRuleH.CONCLUSION_TITLES):
                start = match.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(paper_md)
                content = paper_md[start:end].strip()
                cleaned = clean_markdown_text(content)

                return LimitationsRuleH._find_signal_sentence(cleaned, max_sentences)

        return None

    @staticmethod
    def _extract_from_last_20_percent(paper_md: str, max_sentences: int) -> Optional[str]:
        """在全文后20%找局限性信号句"""
        start_pos = int(len(paper_md) * 0.8)
        last_20 = paper_md[start_pos:]

        cleaned = clean_markdown_text(last_20)
        return LimitationsRuleH._find_signal_sentence(cleaned, max_sentences)

    @staticmethod
    def _find_signal_sentence(text: str, max_sentences: int) -> Optional[str]:
        """在文本中找局限性信号句"""
        all_sentences = extract_first_n_sentences(text, n=len(text), method="regex")

        for signal in LimitationsRuleH.LIMITATION_SIGNALS:
            for j in range(len(all_sentences) - 1, -1, -1):
                sent_lower = all_sentences[j].lower()
                if signal in sent_lower:
                    end_idx = min(len(all_sentences), j + 2)
                    selected = all_sentences[j:end_idx]
                    if selected:
                        return " ".join(selected[:max_sentences])

        return None


if __name__ == "__main__":
    test_md = """
# Conclusion
Our method achieves SOTA results. However, it is computationally expensive.

Manocha, "Efficient generation of motion plans from attribute-based natural language instructions using dynamic constraint mapping," in 2019 International Conference on Robotics and Automation (ICRA). IEEE, 2019, pp.
    """

    result = LimitationsRuleH.extract(test_md)
    print(f"Extracted limitations: {result}")