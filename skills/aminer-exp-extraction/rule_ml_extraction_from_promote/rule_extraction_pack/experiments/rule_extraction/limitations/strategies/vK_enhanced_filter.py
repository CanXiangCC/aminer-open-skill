"""
limitations--策略K--vJ增强过滤

策略描述: 在vJ基础上增加更多过滤规则
  1. 过滤方法介绍："In addition, we propose"/"In our work, we focus"/"We present"
  2. 过滤对比工作："effective methods for"/"existing methods are"
  3. 过滤纯积极内容：无"limitation"/"cannot"/"fails to"等消极词
  4. 过滤"However"但无"our"/"we"的（对比工作转折）

核心思想: 更严格的过滤，宁可漏判不误判
Strategy: vJ + enhanced filtering
"""

import re
import sys
from pathlib import Path
from typing import Optional

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.shared.utils import extract_first_n_sentences, clean_markdown_text


class LimitationsRuleK:
    """局限性提取规则 - Limitations Extraction Rule - K (vJ + enhanced filtering)"""

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

    # === 增强过滤规则 ===

    # 表格标题
    TABLE_PATTERNS = [
        r"^TABLE\s+\d+",
        r"^Table\s+\d+",
        r"Summary of the limitations",
        r"Summary of the",
    ]

    # Future Work
    FUTURE_PATTERNS = [
        r"^FUTURE\s+",
        r"^Future\s+work",
        r"^future\s+directions",
    ]

    # 方法介绍
    METHOD_INTRO_PATTERNS = [
        r"^In addition, we propose",
        r"^In our work, we focus",
        r"^We present",
        r"^In this paper",
        r"^This paper",
        r"^We propose",
        r"^We introduce",
    ]

    # 对比工作（其他方法的优势/局限）
    COMPARE_WORK_PATTERNS = [
        r"effective methods for",
        r"existing methods are",
        r"the effective methods",
        r"state-of-the-art methods are",
        r"sota methods are",
        r"[A-Z][a-z]+\s+\.\s+proposed",  # 作者名+proposed
        r"proposed .* but .* cannot",  # 某方法proposed but cannot...
        r"^[A-Z][a-z]+\s+\([A-Z]+\)\s+utilized",  # 方法名(缩写) utilized...
        r"^[A-Z][a-z]+\s+\([A-Z]+\)\s+proposed",  # 方法名(缩写) proposed...
    ]

    # 积极内容
    POSITIVE_PATTERNS = [
        r"benefits from",
        r"provides several benefits",
        r"has several advantages",
        r"improves performance",
        r"achieves SOTA",
        r"outperforms",
        r"demonstrates improved",
        r"superior performance",
    ]

    # 消极词（必须至少有一个，否则可能是积极内容）
    NEGATIVE_KEYWORDS = [
        "limitation",
        "limitations",
        "cannot",
        "fails to",
        "limited to",
        "constraint",
        "shortcoming",
        "gap",
        "issue",
        "problem",
        "challeng",
        "lacks",
        "insufficient",
        "poor",
        "worse",
        "lower",
        "error",
        "mistake",
        "inadequate",
    ]

    # 背景介绍模式（非本文limitations）
    BACKGROUND_PATTERNS = [
        r"^Due to .* limitations,",  # Due to computational limitations, ...
        r"^.* limitations, .* needs to be",  # limitations, ... needs to be...
    ]

    # Section标题模式（大写，Markdown header）
    SECTION_HEADER_PATTERNS = [
        r"^#+\s*LIMITATIONS?\s*$",
        r"^#+\s*.*LIMITATIONS?.*$",
        r"^LIMITATIONS?$",
        r"^LIMITATIONS? AND",
        r"^CONCLUSIONS?, LIMITATIONS?",
    ]

    # 自指词
    SELF_REFER_KEYWORDS = ["our", "we", "this work", "our approach", "our method"]

    CITATION_PATTERNS = [
        r"[A-Z][a-z]+,\s+[A-Z][a-z]+\s+\w+\s+\d{4}",
        r"\bet\.\s+al\.",
        r"\b(?:in|at)\s+(?:ICRA|CVPR|NeurIPS|ICML|AAAI|ECCV|IJCAI)",
        r"\bpp\.\s+\d+(?:-\d+)?",
        r"\[\d+(?:-\d+)?\]",
        r"\b(?:doi\.org|doi:)",
    ]

    @staticmethod
    def _should_filter(text: str, signal_word: str) -> bool:
        """
        检查文本是否应该被过滤（返回True表示应该过滤）

        新增规则：
        1. 方法介绍
        2. 对比工作
        3. 无消极词（除非是"limitation"本身）
        4. "However"/"but"但无自指（对比工作转折）
        """
        text_lower = text.strip().lower()

        # 检查表格标题
        for pattern in LimitationsRuleK.TABLE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True

        # 检查Future Work
        for pattern in LimitationsRuleK.FUTURE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True

        # 检查方法介绍
        for pattern in LimitationsRuleK.METHOD_INTRO_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True

        # 检查对比工作
        for pattern in LimitationsRuleK.COMPARE_WORK_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True

        # 检查积极内容
        for pattern in LimitationsRuleK.POSITIVE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True

        # === 新增：过滤Section标题（大写LIMITATION）===
        for pattern in LimitationsRuleK.SECTION_HEADER_PATTERNS:
            if re.search(pattern, text):
                return True

        # === 新增：过滤背景介绍 ===
        for pattern in LimitationsRuleK.BACKGROUND_PATTERNS:
            if re.search(pattern, text):
                return True

        # === 新增：必须有消极词 ===
        has_negative = any(kw in text_lower for kw in LimitationsRuleK.NEGATIVE_KEYWORDS)
        # 例外：信号词本身是"limitation"/"limitations"/"shortcoming"/"constraint"
        signal_is_negative = signal_word in ("limitation", "limitations", "shortcoming", "constraint", "limited to", "fails to")

        if not has_negative and not signal_is_negative:
            return True

        # === 新增："However"/"but"/"although"/"despite"/"on the other hand"必须有自指（对比工作检查）===
        if signal_word in ("however", "but", "although", "despite", "on the other hand"):
            has_self_refer = any(kw in text_lower for kw in LimitationsRuleK.SELF_REFER_KEYWORDS)
            if not has_self_refer:
                return True

        return False

    @staticmethod
    def _enhanced_remove_references(paper_md: str) -> str:
        """增强的引用删除"""
        cleaned = LimitationsRuleK._remove_standard_references(paper_md)
        if cleaned != paper_md:
            return cleaned
        return LimitationsRuleK._remove_embedded_citations(paper_md)

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
        """删除混杂引用"""
        for pattern in LimitationsRuleK.CITATION_PATTERNS:
            matches = list(re.finditer(pattern, paper_md, re.IGNORECASE))
            if matches:
                last_match = matches[-1]
                citation_region = paper_md[last_match.start():]
                citation_density = (
                    citation_region.count("et al") + citation_region.count("pp.") +
                    citation_region.count("IEEE") + citation_region.count("ICRA") +
                    citation_region.count("CVPR") + citation_region.count("NeurIPS") +
                    citation_region.count("[1]") + citation_region.count("doi")
                )
                if citation_density >= 3:
                    return paper_md[:last_match.start()].rstrip()
        return paper_md

    @staticmethod
    def extract(paper_md: str, max_sentences: int = 2) -> Optional[str]:
        """提取局限性"""
        md_no_refs = LimitationsRuleK._enhanced_remove_references(paper_md)
        result = LimitationsRuleK._extract_from_conclusion(md_no_refs, max_sentences)
        if result:
            return result
        result = LimitationsRuleK._extract_from_last_20_percent(md_no_refs, max_sentences)
        if result:
            return result
        return None

    @staticmethod
    def _extract_from_conclusion(paper_md: str, max_sentences: int) -> Optional[str]:
        """在Conclusion section中找局限性信号句（带增强过滤）"""
        HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        matches = list(HEADER_RE.finditer(paper_md))
        for i, match in enumerate(matches):
            title = match.group(2).strip().lower()
            if any(kw in title for kw in LimitationsRuleK.CONCLUSION_TITLES):
                start = match.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(paper_md)
                content = paper_md[start:end].strip()
                cleaned = clean_markdown_text(content)
                return LimitationsRuleK._find_signal_sentence(cleaned, max_sentences)
        return None

    @staticmethod
    def _extract_from_last_20_percent(paper_md: str, max_sentences: int) -> Optional[str]:
        """在全文后20%找局限性信号句（带增强过滤）"""
        start_pos = int(len(paper_md) * 0.8)
        last_20 = paper_md[start_pos:]
        cleaned = clean_markdown_text(last_20)
        return LimitationsRuleK._find_signal_sentence(cleaned, max_sentences)

    @staticmethod
    def _find_signal_sentence(text: str, max_sentences: int) -> Optional[str]:
        """在文本中找局限性信号句（带增强过滤）"""
        all_sentences = extract_first_n_sentences(text, n=len(text), method="regex")
        for signal in LimitationsRuleK.LIMITATION_SIGNALS:
            for j in range(len(all_sentences) - 1, -1, -1):
                sent_lower = all_sentences[j].lower()
                if signal in sent_lower:
                    candidate = all_sentences[j]
                    if LimitationsRuleK._should_filter(candidate, signal):
                        continue
                    end_idx = min(len(all_sentences), j + 2)
                    combined = " ".join(all_sentences[j:end_idx])
                    if LimitationsRuleK._should_filter(combined, signal):
                        continue
                    selected = all_sentences[j:end_idx]
                    if selected:
                        return " ".join(selected[:max_sentences])
        return None


if __name__ == "__main__":
    # 测试过滤规则
    test_cases = [
        ("TABLE 14 Summary of the limitations...", "limitation", True, "table"),
        ("In addition, we propose a Contrastive network...", "however", True, "method intro"),
        ("However, the effective methods for extracting...", "however", True, "compare work"),
        ("However, our method has limitations...", "however", False, "valid"),
        ("Our approach achieves SOTA results...", "however", True, "positive"),
        ("In our work, we focus on OOD detection...", "however", True, "work intro"),
        ("This paper presents a novel method...", "however", True, "paper intro"),
    ]

    print("Enhanced Filtering Tests:")
    for text, signal, should_filter, desc in test_cases:
        result = LimitationsRuleK._should_filter(text, signal)
        status = "PASS" if result == should_filter else "FAIL"
        print(f"  [{status}] {desc}: '{text[:45]}...' -> {'FILTER' if result else 'KEEP'}")