"""
limitations--策略G--只删除References（保持vD逻辑）

策略描述: 只删除References，然后进行vD的信号句匹配
Strategy: Remove References only, then vD signal matching
"""

import re
import sys
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.shared.utils import extract_first_n_sentences, clean_markdown_text


class LimitationsRuleG:
    """局限性提取规则 - Limitations Extraction Rule - G (Remove refs + vD)"""

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

    @staticmethod
    def _remove_references(paper_md: str) -> str:
        """删除References section"""
        # References标题模式（支持变体）
        refs_patterns = [
            r"^#{1,3}\s*(?:References|Bibliography|Works Cited)\s*$",
            r"^\s*(?:References|Bibliography)\s*$",
            r"^##?\s*References\s*$",
        ]

        for pattern in refs_patterns:
            match = re.search(pattern, paper_md, re.IGNORECASE | re.MULTILINE)
            if match:
                return paper_md[:match.start()].rstrip()

        return paper_md

    @staticmethod
    def extract(paper_md: str, max_sentences: int = 2) -> Optional[str]:
        """
        提取局限性（只删除References + vD逻辑）

        Args:
            paper_md: 论文markdown文本
            max_sentences: 最大句子数

        Returns:
            Optional[str]: 提取的局限性
        """
        # === 预处理：删除References ===
        md_no_refs = LimitationsRuleG._remove_references(paper_md)

        # === Layer 1: Conclusion中找信号句 ===
        result = LimitationsRuleG._extract_from_conclusion(md_no_refs, max_sentences)
        if result:
            return result

        # === Layer 2: 全文后20%找信号句（原文长度）===
        result = LimitationsRuleG._extract_from_last_20_percent(md_no_refs, max_sentences)
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

            if any(kw in title for kw in LimitationsRuleG.CONCLUSION_TITLES):
                start = match.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(paper_md)
                content = paper_md[start:end].strip()
                cleaned = clean_markdown_text(content)

                # 找信号句
                return LimitationsRuleG._find_signal_sentence(cleaned, max_sentences)

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
        return LimitationsRuleG._find_signal_sentence(cleaned, max_sentences)

    @staticmethod
    def _find_signal_sentence(text: str, max_sentences: int) -> Optional[str]:
        """在文本中找局限性信号句"""
        all_sentences = extract_first_n_sentences(text, n=len(text), method="regex")

        # 从后往前找第一个高优先级信号句
        for signal in LimitationsRuleG.LIMITATION_SIGNALS:
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
# Conclusion
Our method achieves SOTA results on ImageNet. However, it is computationally expensive.

# References
[1] Paper A
    """

    result = LimitationsRuleG.extract(test_md)
    print(f"Extracted limitations: {result}")