"""
limitations--策略v5--三层分层

策略描述: 三层分层fallback策略（与conclusion分离实现）
Layer 1: 增强标题匹配
Layer 2: Conclusion/Discussion内搜索 + 自指关键词验证
Layer 3: 后50%文章 + 自指+limitations关键词双重验证

改进 Improvement: 预处理阶段移除Introduction/Related Work等无关section
"""

import re
import sys
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.shared.utils import extract_first_n_sentences, clean_markdown_text


class LimitationsRuleV5:
    """局限性提取规则 - Limitations Extraction Rule - V5 (Layered Fallback)"""

    # Layer 1: Limitations标题关键词
    LAYER1_TITLES = [
        "limitation",
        "limitations",
        "limitations and future work",
        "limitation and failure cases",
    ]

    # Layer 2: Conclusion/Discussion标题 + limitations关键词
    LAYER2_CONCLUSION_TITLES = [
        "conclusion",
        "conclusions",
        "conclusion and future work",
    ]

    LAYER2_DISCUSSION_TITLES = [
        "discussion",
        "discussion and conclusion",
    ]

    LAYER2_LIMITATION_KEYWORDS = [
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

    # Layer 2 自指关键词（确保是论文自己的limitations）
    LAYER2_SELF_REFER = [
        "our",
        "proposed",
        "this work",
        "we",
    ]

    # Layer 3: 总结性关键词（自指 + limitations）
    LAYER3_SELF_REFER = [
        "our approach has",
        "our method",
        "proposed method",
        "our work",
        "this approach",
    ]

    LAYER3_LIMITATION_KEYWORDS = [
        "limitation",
        "limitations",
        "shortcoming",
        "weakness",
        "drawback",
        "constraint",
        "challenge",
        "however",
        "but",
        "first",
        "second",
        "note",
        "unfortunately",
    ]

    # 需要排除的section（避免提取到其他方法的limitations）
    EXCLUDED_SECTIONS = [
        "introduction",
        "related work",
        "background",
        "abstract",
        "references",
    ]

    # ponytail: 统一的header检测，支持Markdown/罗马数字/数字/全大写格式
    _HEADER_RE = re.compile(
        r"^" + r"(#{1,6}\s+.+)|" +  # # Introduction
        r"([IVXLCDM]+\s*[.)]\s+.+)|" +  # I. INTRODUCTION, II) OVERVIEW
        r"(\d+(?:\.\d+)*\s+[.)]\s+.+)|" +  # 1. Introduction, 1.1 Background
        r"^[A-Z\s]{10,}$"  # INTRODUCTION (全大写)
        , re.MULTILINE
    )

    @staticmethod
    def _extract_header_title(header_text: str) -> str:
        """从header文本中提取标题（移除前缀）"""
        header_text = header_text.strip()

        # Markdown格式
        if header_text.startswith('#'):
            return re.sub(r'^#{1,6}\s+', '', header_text).strip()

        # 罗马数字前缀: I. INTRODUCTION -> INTRODUCTION
        roman_match = re.match(r'^[IVXLCDM]+\s*[.)]\s*', header_text, re.IGNORECASE)
        if roman_match:
            return header_text[roman_match.end():].strip()

        # 数字前缀: 1. Introduction -> Introduction
        num_match = re.match(r'^\d+(?:\.\d+)*\s+[.)]\s*', header_text)
        if num_match:
            return header_text[num_match.end():].strip()

        return header_text

    @staticmethod
    def _preprocess_sections(paper_md: str) -> str:
        """
        预处理：移除无关section（Introduction, Related Work等）
        Preprocess: Remove irrelevant sections (Introduction, Related Work, etc.)

        支持多种header格式:
        - Markdown: # Introduction
        - 罗马数字: I. INTRODUCTION
        - 数字: 1. Introduction, 1.1 Background
        - 全大写: INTRODUCTION

        Args:
            paper_md: 论文markdown文本 - Paper markdown text

        Returns:
            str: 清理后的markdown - Cleaned markdown
        """
        matches = list(LimitationsRuleV5._HEADER_RE.finditer(paper_md))

        if not matches:
            return paper_md

        # 需要排除的section标题（部分匹配，小写）
        EXCLUDED_TITLES = [
            "introduction",
            "related work",
            "background",
            "abstract",
            "references",
            "acknowledg",  # acknowledgments, acknowledgement
        ]

        # 构建需要保留的section范围（即不被排除的范围）
        keep_ranges = []
        last_pos = 0

        for i, match in enumerate(matches):
            header_text = match.group().strip()
            title = LimitationsRuleV5._extract_header_title(header_text).lower()

            # 检查是否需要排除
            if any(ex in title for ex in EXCLUDED_TITLES):
                # 记录上一个保留段的结束位置
                if match.start() > last_pos:
                    keep_ranges.append((last_pos, match.start()))

                # 跳过这个section，移动last_pos到下一个section开始
                next_start = matches[i + 1].start() if i + 1 < len(matches) else len(paper_md)
                last_pos = next_start

        # 保留最后一段
        if last_pos < len(paper_md):
            keep_ranges.append((last_pos, len(paper_md)))

        # 拼接保留的内容
        if not keep_ranges:
            return paper_md

        return "".join(paper_md[start:end] for start, end in keep_ranges)

    @staticmethod
    def extract(paper_md: str, max_sentences: int = 2) -> Optional[str]:
        """
        提取局限性（三层分层fallback）
        Extract limitations (3-layer fallback)

        策略 Strategy:
        Layer 1: 标题匹配（limitations相关）
        Layer 2: Conclusion/Discussion内搜索 + 自指验证
        Layer 3: 后50%文章 + 自指+limitations关键词双重验证

        改进: 预处理移除Introduction/Related Work等无关section

        Args:
            paper_md: 论文markdown文本 - Paper markdown text
            max_sentences: 最大句子数 - Maximum number of sentences

        Returns:
            Optional[str]: 提取的局限性，未找到返回None - Extracted limitations, None if not found
        """
        # === 预处理：移除无关section ===
        cleaned_md = LimitationsRuleV5._preprocess_sections(paper_md)

        # === Layer 1: 标题匹配 ===
        result = LimitationsRuleV5._extract_by_title_matching(cleaned_md, max_sentences)
        if result:
            return result

        # === Layer 2: Conclusion/Discussion内搜索 + 自指验证 ===
        result = LimitationsRuleV5._extract_from_sections_with_validation(cleaned_md, max_sentences)
        if result:
            return result

        # === Layer 3: 后50% + 双重验证 ===
        result = LimitationsRuleV5._extract_from_last_half(cleaned_md, max_sentences)
        if result:
            return result

        return None

    @staticmethod
    def _extract_by_title_matching(paper_md: str, max_sentences: int) -> Optional[str]:
        """Layer 1: 标题匹配（使用统一header检测）"""
        matches = list(LimitationsRuleV5._HEADER_RE.finditer(paper_md))

        for i, match in enumerate(matches):
            header_text = match.group().strip()
            title = LimitationsRuleV5._extract_header_title(header_text).lower()

            if any(kw in title for kw in LimitationsRuleV5.LAYER1_TITLES):
                return LimitationsRuleV5._extract_section_content(
                    paper_md, i, matches, max_sentences
                )

        return None

    @staticmethod
    def _extract_from_sections_with_validation(paper_md: str, max_sentences: int) -> Optional[str]:
        """Layer 2: Conclusion/Discussion内搜索 + 自指验证（使用统一header检测）"""
        matches = list(LimitationsRuleV5._HEADER_RE.finditer(paper_md))

        # 合并目标section标题
        target_titles = (
            LimitationsRuleV5.LAYER2_CONCLUSION_TITLES +
            LimitationsRuleV5.LAYER2_DISCUSSION_TITLES
        )

        for i, match in enumerate(matches):
            header_text = match.group().strip()
            title = LimitationsRuleV5._extract_header_title(header_text).lower()

            # 检查是否是目标section
            if any(kw in title for kw in target_titles):
                # 提取section内容
                start = match.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(paper_md)
                content = paper_md[start:end].strip()
                cleaned = clean_markdown_text(content)
                content_lower = cleaned.lower()

                # 验证1: 包含limitations关键词
                has_limitation_kw = any(kw in content_lower for kw in LimitationsRuleV5.LAYER2_LIMITATION_KEYWORDS)

                # 验证2: 包含自指关键词（确保是本文的limitations）
                has_self_refer = any(kw in content_lower for kw in LimitationsRuleV5.LAYER2_SELF_REFER)

                if has_limitation_kw and has_self_refer:
                    sentences = extract_first_n_sentences(cleaned, n=max_sentences, method="regex")
                    if sentences:
                        return " ".join(sentences)

        return None

    @staticmethod
    def _extract_from_last_half(cleaned_md: str, max_sentences: int) -> Optional[str]:
        """Layer 3: 后50% + 双重验证"""
        # 注意: cleaned_md 已经移除了无关section，不需要再排除section

        # 1. 取后50%
        half_pos = len(cleaned_md) // 2
        last_half = cleaned_md[half_pos:]

        # 2. 按段落分割
        paragraphs = re.split(r"\n{2,}", last_half.strip())

        # 3. 找到最相关的段落
        best_para = None
        best_score = 0

        for para in paragraphs:
            para_lower = para.lower()

            # 计算自指关键词分数 (权重3)
            self_refer_score = sum(3 for kw in LimitationsRuleV5.LAYER3_SELF_REFER if kw in para_lower)

            # 计算limitations关键词分数 (权重1)
            limitation_score = sum(1 for kw in LimitationsRuleV5.LAYER3_LIMITATION_KEYWORDS if kw in para_lower)

            total_score = self_refer_score + limitation_score

            if total_score > best_score and total_score >= 3:  # 至少1个自指+1个limitation
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
        """提取section内容的辅助函数"""
        start = matches[match_idx].end()
        end = matches[match_idx + 1].start() if match_idx + 1 < len(matches) else len(paper_md)
        content = paper_md[start:end].strip()
        cleaned = clean_markdown_text(content)
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
Our results are promising. However, our approach has limitations. Future work...

# Discussion
In summary, our method works well. Our proposed approach has some constraints.
    """

    result = LimitationsRuleV5.extract(test_md)
    print(f"Extracted limitations: {result}")