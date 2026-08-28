"""
limitations--策略F--预处理vE（删除Introduction/References）

策略描述: 先删除Introduction/References，再进行vE的信号句匹配
Strategy: Preprocess (remove Introduction/References), then vE signal matching
"""

import re
import sys
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.shared.utils import extract_first_n_sentences, clean_markdown_text


class LimitationsRuleF:
    """局限性提取规则 - Limitations Extraction Rule - F (Preprocess + vE)"""

    # Conclusion标题
    CONCLUSION_TITLES = [
        "conclusion",
        "conclusions",
        "discussion",
        "discussion and conclusion",
    ]

    # 局限性信号词（优先级从高到低）
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
        "cannot",
        "fails to",
    ]

    # 需要删除的section标题
    EXCLUDED_SECTIONS = [
        "introduction",
        "references",
        "bibliography",
        "acknowledg",  # acknowledgments, acknowledgement
    ]

    @staticmethod
    def _preprocess_sections(paper_md: str) -> str:
        """删除Introduction/References等无关section"""
        # 统一header检测（支持Markdown/罗马数字/数字）
        HEADER_RE = re.compile(
            r"^" + r"(#{1,6}\s+.+)|" +
            r"([IVXLCDM]+\s*[.)]\s+.+)|" +
            r"(\d+(?:\.\d+)*\s+[.)]\s+.+)|" +
            r"^[A-Z\s]{10,}$",
            re.MULTILINE
        )

        matches = list(HEADER_RE.finditer(paper_md))

        if not matches:
            return paper_md

        # 构建需要保留的section范围
        keep_ranges = []
        last_pos = 0

        for i, match in enumerate(matches):
            header_text = match.group().strip()
            title = LimitationsRuleF._extract_header_title(header_text).lower()

            # 检查是否需要删除
            if any(ex in title for ex in LimitationsRuleF.EXCLUDED_SECTIONS):
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
        提取局限性（预处理 + vE逻辑）

        Args:
            paper_md: 论文markdown文本
            max_sentences: 最大句子数

        Returns:
            Optional[str]: 提取的局限性
        """
        # === 预处理：删除Introduction/References ===
        cleaned_md = LimitationsRuleF._preprocess_sections(paper_md)

        # === Layer 1: Conclusion中找信号句 ===
        result = LimitationsRuleF._extract_from_conclusion(cleaned_md, max_sentences)
        if result:
            return result

        # === Layer 2: 全文后20%找信号句 ===
        result = LimitationsRuleF._extract_from_last_20_percent(cleaned_md, max_sentences)
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

            if any(kw in title for kw in LimitationsRuleF.CONCLUSION_TITLES):
                start = match.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(paper_md)
                content = paper_md[start:end].strip()
                cleaned = clean_markdown_text(content)

                # 找信号句
                return LimitationsRuleF._find_signal_sentence(cleaned, max_sentences)

        return None

    @staticmethod
    def _extract_from_last_20_percent(paper_md: str, max_sentences: int) -> Optional[str]:
        """在全文后20%找局限性信号句"""
        # 取后20%
        start_pos = int(len(paper_md) * 0.8)
        last_20 = paper_md[start_pos:]

        # 清理
        cleaned = clean_markdown_text(last_20)

        # 找信号句
        return LimitationsRuleF._find_signal_sentence(cleaned, max_sentences)

    @staticmethod
    def _find_signal_sentence(text: str, max_sentences: int) -> Optional[str]:
        """在文本中找局限性信号句"""
        all_sentences = extract_first_n_sentences(text, n=len(text), method="regex")

        # 从后往前找第一个高优先级信号句
        for signal in LimitationsRuleF.LIMITATION_SIGNALS:
            for j in range(len(all_sentences) - 1, -1, -1):
                sent_lower = all_sentences[j].lower()
                if signal in sent_lower:
                    # 取信号句+后1句
                    end_idx = min(len(all_sentences), j + 2)
                    selected = all_sentences[j:end_idx]
                    if selected:
                        return " ".join(selected[:max_sentences])

        return None


if __name__ == "__main__":
    test_md = """
# Introduction
This paper presents a new method for face recognition.

# Conclusion
Our method achieves SOTA results on ImageNet. However, it is computationally expensive.
    """

    result = LimitationsRuleF.extract(test_md)
    print(f"Extracted limitations: {result}")