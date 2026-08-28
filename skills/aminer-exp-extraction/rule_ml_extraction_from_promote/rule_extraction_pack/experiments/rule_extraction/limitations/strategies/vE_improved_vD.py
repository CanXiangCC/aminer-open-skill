"""
limitations--策略E--改进vD（取消Future Work + 全文后20% fallback）

策略描述: Conclusion中找信号句，失败则全文后20%找
Strategy: Find signal sentences in Conclusion, fallback to last 20% of paper
"""

import re
import sys
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.shared.utils import extract_first_n_sentences, clean_markdown_text


class LimitationsRuleE:
    """局限性提取规则 - Limitations Extraction Rule - E (Improved vD)"""

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
    def extract(paper_md: str, max_sentences: int = 2) -> Optional[str]:
        """
        提取局限性（改进vD）

        Args:
            paper_md: 论文markdown文本
            max_sentences: 最大句子数

        Returns:
            Optional[str]: 提取的局限性
        """
        # === Layer 1: Conclusion中找信号句 ===
        result = LimitationsRuleE._extract_from_conclusion(paper_md, max_sentences)
        if result:
            return result

        # === Layer 2: 全文后20%找信号句 ===
        result = LimitationsRuleE._extract_from_last_20_percent(paper_md, max_sentences)
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

            if any(kw in title for kw in LimitationsRuleE.CONCLUSION_TITLES):
                start = match.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(paper_md)
                content = paper_md[start:end].strip()
                cleaned = clean_markdown_text(content)

                # 找信号句
                return LimitationsRuleE._find_signal_sentence(cleaned, max_sentences)

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
        return LimitationsRuleE._find_signal_sentence(cleaned, max_sentences)

    @staticmethod
    def _find_signal_sentence(text: str, max_sentences: int) -> Optional[str]:
        """在文本中找局限性信号句"""
        all_sentences = extract_first_n_sentences(text, n=len(text), method="regex")

        # 从后往前找第一个高优先级信号句
        for signal in LimitationsRuleE.LIMITATION_SIGNALS:
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
    """

    result = LimitationsRuleE.extract(test_md)
    print(f"Extracted limitations: {result}")