"""
limitations--策略J--vH+严格过滤

策略描述: vH基础上添加严格过滤规则
  1. 恢复"however"/"but"（配合自指验证使用）
  2. 排除表格标题/行（"TABLE"/"Summary of"/"•"）
  3. 排除Future Work（"FUTURE"/"future work"）
  4. 排除Conclusion开头句（"We present"/"In this paper"）
  5. 排除积极内容（"benefits"/"advantages"/"improves"）

核心思想: 宁可漏判不误判，过滤掉明显不相关的内容
Strategy: vH + strict filtering rules
"""

import re
import sys
from pathlib import Path
from typing import Optional

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.shared.utils import extract_first_n_sentences, clean_markdown_text


class LimitationsRuleJ:
    """局限性提取规则 - Limitations Extraction Rule - J (vH + strict filtering)"""

    CONCLUSION_TITLES = [
        "conclusion",
        "conclusions",
        "discussion",
        "discussion and conclusion",
    ]

    # 恢复原始信号词
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

    # === 过滤规则（排除明显不相关的内容）===
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

    # Conclusion开头句（方法介绍）
    CONCLUSION_INTRO_PATTERNS = [
        r"^We present",
        r"^In this paper",
        r"^This paper",
        r"^We propose",
        r"^We introduce",
        r"^This work",
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
    def _should_filter(text: str) -> bool:
        """
        检查文本是否应该被过滤（返回True表示应该过滤）

        过滤条件：
        1. 表格标题/行
        2. Future Work
        3. Conclusion开头句
        4. 积极内容
        """
        text_clean = text.strip()

        # 检查表格标题
        for pattern in LimitationsRuleJ.TABLE_PATTERNS:
            if re.search(pattern, text_clean, re.IGNORECASE):
                return True

        # 检查Future Work
        for pattern in LimitationsRuleJ.FUTURE_PATTERNS:
            if re.search(pattern, text_clean, re.IGNORECASE):
                return True

        # 检查Conclusion开头句
        for pattern in LimitationsRuleJ.CONCLUSION_INTRO_PATTERNS:
            if re.search(pattern, text_clean, re.IGNORECASE):
                return True

        # 检查积极内容
        for pattern in LimitationsRuleJ.POSITIVE_PATTERNS:
            if re.search(pattern, text_clean, re.IGNORECASE):
                return True

        return False

    @staticmethod
    def _enhanced_remove_references(paper_md: str) -> str:
        """增强的引用删除：先尝试标准References，失败则检测混杂引用"""
        cleaned = LimitationsRuleJ._remove_standard_references(paper_md)
        if cleaned != paper_md:
            return cleaned
        return LimitationsRuleJ._remove_embedded_citations(paper_md)

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
        for pattern in LimitationsRuleJ.CITATION_PATTERNS:
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
        提取局限性（vJ: vH + 严格过滤）

        Args:
            paper_md: 论文markdown文本
            max_sentences: 最大句子数

        Returns:
            Optional[str]: 提取的局限性
        """
        md_no_refs = LimitationsRuleJ._enhanced_remove_references(paper_md)

        # === Layer 1: Conclusion中找信号句（带严格过滤）===
        result = LimitationsRuleJ._extract_from_conclusion(md_no_refs, max_sentences)
        if result:
            return result

        # === Layer 2: 全文后20%找信号句（带严格过滤）===
        result = LimitationsRuleJ._extract_from_last_20_percent(md_no_refs, max_sentences)
        if result:
            return result

        # === Layer 3取消，直接返回None ===
        return None

    @staticmethod
    def _extract_from_conclusion(paper_md: str, max_sentences: int) -> Optional[str]:
        """在Conclusion section中找局限性信号句（带严格过滤）"""
        HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        matches = list(HEADER_RE.finditer(paper_md))

        for i, match in enumerate(matches):
            title = match.group(2).strip().lower()

            if any(kw in title for kw in LimitationsRuleJ.CONCLUSION_TITLES):
                start = match.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(paper_md)
                content = paper_md[start:end].strip()
                cleaned = clean_markdown_text(content)

                return LimitationsRuleJ._find_signal_sentence(cleaned, max_sentences)

        return None

    @staticmethod
    def _extract_from_last_20_percent(paper_md: str, max_sentences: int) -> Optional[str]:
        """在全文后20%找局限性信号句（带严格过滤）"""
        start_pos = int(len(paper_md) * 0.8)
        last_20 = paper_md[start_pos:]

        cleaned = clean_markdown_text(last_20)
        return LimitationsRuleJ._find_signal_sentence(cleaned, max_sentences)

    @staticmethod
    def _find_signal_sentence(text: str, max_sentences: int) -> Optional[str]:
        """
        在文本中找局限性信号句（带严格过滤）

        新增：严格过滤规则，排除明显不相关内容
        """
        all_sentences = extract_first_n_sentences(text, n=len(text), method="regex")

        for signal in LimitationsRuleJ.LIMITATION_SIGNALS:
            for j in range(len(all_sentences) - 1, -1, -1):
                sent_lower = all_sentences[j].lower()

                if signal in sent_lower:
                    # === 严格过滤 ===
                    candidate = all_sentences[j]
                    if LimitationsRuleJ._should_filter(candidate):
                        continue

                    # 取信号句+后1句，组合后再检查
                    end_idx = min(len(all_sentences), j + 2)
                    combined = " ".join(all_sentences[j:end_idx])

                    if LimitationsRuleJ._should_filter(combined):
                        continue

                    # 通过过滤，返回结果
                    selected = all_sentences[j:end_idx]
                    if selected:
                        return " ".join(selected[:max_sentences])

        return None


if __name__ == "__main__":
    # 测试过滤规则
    test_cases = [
        ("TABLE 14 Summary of the limitations...", True, "table caption"),
        ("FUTURE RESEARCH DIRECTIONS ...", True, "future work"),
        ("We present a novel point cloud completion...", True, "conclusion intro"),
        ("This benefits from the fact that...", True, "positive content"),
        ("However, our method has limitations...", False, "valid limitation"),
        ("But our approach fails to handle...", False, "valid limitation"),
    ]

    print("Filtering Rule Tests:")
    for text, should_filter, desc in test_cases:
        result = LimitationsRuleJ._should_filter(text)
        status = "PASS" if result == should_filter else "FAIL"
        print(f"  [{status}] {desc}: {text[:50]}... -> {'FILTER' if result else 'KEEP'}")