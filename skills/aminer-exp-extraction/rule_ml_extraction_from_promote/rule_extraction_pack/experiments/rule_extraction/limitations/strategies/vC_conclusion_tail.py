"""
limitations--策略C--Conclusion末尾找limitations

策略描述: 在Conclusion/Discussion末尾查找limitations关键词句
Strategy: Find limitation keyword sentences at the end of Conclusion/Discussion
"""

import re
import sys
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.shared.utils import extract_first_n_sentences, clean_markdown_text


class LimitationsRuleC:
    """局限性提取规则 - Limitations Extraction Rule - C (Conclusion tail)"""

    # Conclusion/Discussion标题
    TARGET_TITLES = [
        "conclusion",
        "conclusions",
        "discussion",
        "discussion and conclusion",
    ]

    # Limitations信号词
    LIMITATION_SIGNALS = [
        "limitation",
        "limitations",
        "shortcoming",
        "weakness",
        "constraint",
        "however",
        "but",
        "although",
        "despite",
        "not",
        "cannot",
        "fails to",
        "limited to",
    ]

    @staticmethod
    def extract(paper_md: str, max_sentences: int = 2) -> Optional[str]:
        """
        提取局限性（Conclusion末尾找limitations关键词句）

        Args:
            paper_md: 论文markdown文本
            max_sentences: 最大句子数

        Returns:
            Optional[str]: 提取的局限性
        """
        HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        matches = list(HEADER_RE.finditer(paper_md))

        for i, match in enumerate(matches):
            title = match.group(2).strip().lower()

            if any(kw in title for kw in LimitationsRuleC.TARGET_TITLES):
                start = match.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(paper_md)
                content = paper_md[start:end].strip()
                cleaned = clean_markdown_text(content)

                # 获取所有句子
                all_sentences = extract_first_n_sentences(cleaned, n=len(cleaned), method="regex")

                # 从后往前找第一个包含limitations信号的句子
                for j in range(len(all_sentences) - 1, -1, -1):
                    sent_lower = all_sentences[j].lower()
                    if any(signal in sent_lower for signal in LimitationsRuleC.LIMITATION_SIGNALS):
                        # 找到后，取它+前面的句子（最多max_sentences）
                        start_idx = max(0, j - max_sentences + 1)
                        selected = all_sentences[start_idx:j + 1]
                        return " ".join(selected[:max_sentences])

        return None


if __name__ == "__main__":
    test_md = """
# Conclusion
Our method achieves SOTA results on ImageNet. However, it is computationally expensive and requires large datasets.
    """

    result = LimitationsRuleC.extract(test_md)
    print(f"Extracted limitations: {result}")