"""
conclusion--策略v5--三层分层

策略描述: 三层分层fallback策略
Layer 1: 增强标题匹配 (v1+v2合并)
Layer 2: Discussion section + 自指关键词验证
Layer 3: 后50%文章 + 自指+结论关键词双重验证
"""

import re
import sys
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.shared.utils import extract_first_n_sentences, clean_markdown_text


class ConclusionRuleV5:
    """结论提取规则 - Conclusion Extraction Rule - V5 (Layered Fallback)"""

    # Layer 1: 增强标题匹配关键词
    LAYER1_TITLES = [
        "conclusion",
        "conclusions",
    ]

    # Layer 1: 总结信号关键词（用于定位真正结论）
    LAYER1_SUMMARY_SIGNALS = [
        "overall", "in summary", "to summarize", "in conclusion",
        "finally", "taken together", "collectively", "conclude"
    ]

    LAYER1_PATTERNS = [
        r"^conclusions?$",  # 基础
        r"^[ivxlcdm]+\.\s+conclusions?$",  # 罗马数字: VII. Conclusion
        r"^[ivxlcdm]+\)\s+conclusions?$",  # 罗马数字: VII) Conclusion
        r"^\d+\.\s+conclusions?$",  # 数字: 7. Conclusion
        r"^section\s+\d+\.?\d*\s*:?\s*conclusions?$",  # Section 7: Conclusion
        r"conclusion\s+and\s+future\s+work",  # 组合
    ]

    # Layer 2: Discussion标题 + 自指关键词
    LAYER2_TITLES = [
        "discussion",
        "discussion and conclusion",
        "summary and discussion",
        "concluding remarks",
    ]

    LAYER2_SELF_REFER = [
        "our proposed",
        "our method",
        "our approach",
        "this work",
        "we show",
        "we demonstrate",
        "we found",
    ]

    LAYER2_CONCLUSION_SIGNALS = [
        "in summary",
        "to summarize",
        "in conclusion",
        "overall",
        "finally",
        "taken together",
        "collectively",
    ]

    # Layer 3: 总结性关键词（自指 + 结论信号）
    LAYER3_SELF_REFER = [
        "our results show",
        "we demonstrate that",
        "we found that",
        "this study shows",
        "our findings indicate",
        "this work shows",
        "we show that",
    ]

    LAYER3_CONCLUSION_KEYWORDS = [
        "conclude",  # in conclusion, to conclude
        "result",  # results show, our results
        "achieve",  # achieves, achieved
        "demonstrate",  # demonstrates, demonstrated
        "show",  # shows, showed
        "finding",  # findings, main findings
        "improvement",  # improvements
        "outperform",  # outperforms, outperformed
        "contribution",  # contribution, contributions
    ]

    # 需要排除的section（避免提取到不相关内容）
    EXCLUDED_SECTIONS = [
        "introduction",
        "related work",
        "background",
        "abstract",
        "references",
    ]

    @staticmethod
    def extract(paper_md: str, max_sentences: int = 3) -> Optional[str]:
        """
        提取结论（三层分层fallback）
        Extract conclusion (3-layer fallback)

        策略 Strategy:
        Layer 1: 增强标题匹配（conclusion相关）
        Layer 2: Discussion section + 自指关键词验证
        Layer 3: 后50%文章 + 自指+结论关键词双重验证

        Args:
            paper_md: 论文markdown文本 - Paper markdown text
            max_sentences: 最大句子数 - Maximum number of sentences

        Returns:
            Optional[str]: 提取的结论，未找到返回None - Extracted conclusion, None if not found
        """
        # === Layer 1: 增强标题匹配 ===
        result = ConclusionRuleV5._extract_by_title_matching(paper_md, max_sentences)
        if result:
            return result

        # === Layer 2: Discussion section + 自指验证 ===
        result = ConclusionRuleV5._extract_from_discussion(paper_md, max_sentences)
        if result:
            return result

        # === Layer 3: 后50% + 关键词验证 ===
        result = ConclusionRuleV5._extract_from_last_half(paper_md, max_sentences)
        if result:
            return result

        return None

    @staticmethod
    def _extract_by_title_matching(paper_md: str, max_sentences: int) -> Optional[str]:
        """Layer 1: 增强标题匹配"""
        HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        matches = list(HEADER_RE.finditer(paper_md))

        for i, match in enumerate(matches):
            title = match.group(2).strip().lower()

            # 基础关键词匹配 (v1)
            if any(kw in title for kw in ConclusionRuleV5.LAYER1_TITLES):
                return ConclusionRuleV5._extract_conclusion_content(
                    paper_md, i, matches, max_sentences
                )

            # 正则模式匹配 (v2增强)
            for pattern in ConclusionRuleV5.LAYER1_PATTERNS:
                if re.search(pattern, title, re.IGNORECASE):
                    return ConclusionRuleV5._extract_conclusion_content(
                        paper_md, i, matches, max_sentences
                    )

        return None

    @staticmethod
    def _extract_from_discussion(paper_md: str, max_sentences: int) -> Optional[str]:
        """Layer 2: Discussion section + 自指关键词验证"""
        HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        matches = list(HEADER_RE.finditer(paper_md))

        for i, match in enumerate(matches):
            title = match.group(2).strip().lower()

            # 检查是否是Discussion section
            if any(kw in title for kw in ConclusionRuleV5.LAYER2_TITLES):
                # 提取section内容
                start = match.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(paper_md)
                content = paper_md[start:end].strip()
                cleaned = clean_markdown_text(content)
                content_lower = cleaned.lower()

                # 验证1: 包含自指关键词
                has_self_refer = any(kw in content_lower for kw in ConclusionRuleV5.LAYER2_SELF_REFER)

                # 验证2: 包含结论信号
                has_conclusion_signal = any(kw in content_lower for kw in ConclusionRuleV5.LAYER2_CONCLUSION_SIGNALS)

                if has_self_refer and has_conclusion_signal:
                    sentences = extract_first_n_sentences(cleaned, n=max_sentences, method="regex")
                    if sentences:
                        return " ".join(sentences)

        return None

    @staticmethod
    def _extract_from_last_half(paper_md: str, max_sentences: int) -> Optional[str]:
        """Layer 3: 后50%文章 + 关键词双重验证"""
        # 1. 移除References section
        ref_pattern = r"#+\s*references?\s*$"
        if re.search(ref_pattern, paper_md, re.IGNORECASE):
            paper_md = re.split(ref_pattern, paper_md, flags=re.IGNORECASE)[0]

        # 2. 取后50%
        half_pos = len(paper_md) // 2
        last_half = paper_md[half_pos:]

        # 3. 移除headers
        HEADER_RE = re.compile(r"^#{1,6}\s+.+$", re.MULTILINE)
        clean_half = HEADER_RE.sub("", last_half)

        # 4. 按段落分割
        paragraphs = re.split(r"\n{2,}", clean_half.strip())

        # 5. 排除危险section内的段落
        paragraphs = ConclusionRuleV5._filter_out_excluded_sections(paragraphs, paper_md)

        # 6. 找到最相关的段落
        best_para = None
        best_score = 0

        for para in paragraphs:
            para_lower = para.lower()

            # 计算自指关键词分数 (权重3)
            self_refer_score = sum(3 for kw in ConclusionRuleV5.LAYER3_SELF_REFER if kw in para_lower)

            # 计算结论关键词分数 (权重1)
            conclusion_score = sum(1 for kw in ConclusionRuleV5.LAYER3_CONCLUSION_KEYWORDS if kw in para_lower)

            total_score = self_refer_score + conclusion_score

            if total_score > best_score and total_score >= 3:  # 至少有1个自指关键词
                best_score = total_score
                best_para = para

        if best_para and best_score > 0:
            cleaned = clean_markdown_text(best_para)
            sentences = extract_first_n_sentences(cleaned, n=max_sentences, method="regex")
            if sentences:
                return " ".join(sentences)

        return None

    @staticmethod
    def _extract_section_content(paper_md: str, match_idx: int, matches: list, max_sentences: int) -> Optional[str]:
        """提取section内容的辅助函数（用于Layer 2/3）"""
        start = matches[match_idx].end()
        end = matches[match_idx + 1].start() if match_idx + 1 < len(matches) else len(paper_md)
        content = paper_md[start:end].strip()
        cleaned = clean_markdown_text(content)
        sentences = extract_first_n_sentences(cleaned, n=max_sentences, method="regex")
        if sentences:
            return " ".join(sentences)
        return None

    @staticmethod
    def _find_summary_signal_sentence(text: str) -> Optional[int]:
        """找到包含总结信号的句子索引"""
        sentences = extract_first_n_sentences(text, n=len(text), method="regex")
        for i, sent in enumerate(sentences):
            sent_lower = sent.lower()
            if any(signal in sent_lower for signal in ConclusionRuleV5.LAYER1_SUMMARY_SIGNALS):
                return i
        return None

    @staticmethod
    def _extract_conclusion_content(paper_md: str, match_idx: int, matches: list, max_sentences: int) -> Optional[str]:
        """智能提取Conclusion section内容（总结信号优先，否则取有效段落末尾）"""
        start = matches[match_idx].end()
        end = matches[match_idx + 1].start() if match_idx + 1 < len(matches) else len(paper_md)
        content = paper_md[start:end].strip()
        cleaned = clean_markdown_text(content)

        # 1. 尝试找总结信号句
        signal_sentence_idx = ConclusionRuleV5._find_summary_signal_sentence(cleaned)
        if signal_sentence_idx is not None:
            # 提取: 前1句 + 信号句 + 后1句
            all_sentences = extract_first_n_sentences(cleaned, n=len(cleaned), method="regex")
            result = all_sentences[max(0, signal_sentence_idx - 1):signal_sentence_idx + 2]
            if len(result) >= 2:  # 至少有2句（信号句+前/后1句）
                return " ".join(result[:max_sentences])

        # 2. 没有信号句，跳过Limitations/Future Work等子标题，取之前的内容
        sub_section_markers = [
            r"\blimitations\b",
            r"\bfuture work\b",
            r"\breferences\b",
            r"\b acknowledgement",
        ]
        cut_pos = len(cleaned)
        for marker in sub_section_markers:
            match = re.search(marker, cleaned, re.IGNORECASE)
            if match and match.start() < cut_pos:
                cut_pos = match.start()

        pre_subsection = cleaned[:cut_pos].strip()
        if not pre_subsection:
            return None

        # 取内容部分的最后N句
        all_sentences = extract_first_n_sentences(pre_subsection, n=len(pre_subsection), method="regex")
        if len(all_sentences) >= max_sentences:
            return " ".join(all_sentences[-max_sentences:])
        elif all_sentences:
            return " ".join(all_sentences)

        return None

    @staticmethod
    def _filter_out_excluded_sections(paragraphs: list, paper_md: str) -> list:
        """排除危险section内的段落"""
        if not paragraphs:
            return paragraphs

        # 计算每个段落在哪个section
        HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        matches = list(HEADER_RE.finditer(paper_md))

        excluded_paragraphs = []
        current_section = "start"
        match_idx = 0

        for para in paragraphs:
            # 更新当前section
            while match_idx < len(matches):
                header_start = matches[match_idx].start()
                if para.find(paper_md[header_start:]) >= 0:
                    current_section = matches[match_idx].group(2).strip().lower()
                    match_idx += 1
                    break
                match_idx += 1

            # 排除危险section
            if not any(excluded in current_section for excluded in ConclusionRuleV5.EXCLUDED_SECTIONS):
                excluded_paragraphs.append(para)

        return excluded_paragraphs


if __name__ == "__main__":
    # 测试 - Test
    test_md = """
# Introduction
This is introduction.

# Results
Some results.

# Discussion
In summary, our proposed method achieves SOTA results on ImageNet. We demonstrate that...

# References
[1] Paper
    """

    result = ConclusionRuleV5.extract(test_md)
    print(f"Extracted conclusion: {result}")