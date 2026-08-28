"""
limitations--策略D--Conclusion末尾找局限性信号句

策略描述: 类conclusion v5，在Conclusion末尾找"However/But/Although"等信号句
Strategy: Find signal sentences (However/But/Although) at the end of Conclusion
"""

import re
import sys
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.shared.utils import extract_first_n_sentences, clean_markdown_text


class LimitationsRuleD:
    """局限性提取规则 - Limitations Extraction Rule - D (Conclusion signals)"""

    # Conclusion标题
    CONCLUSION_TITLES = [
        "conclusion",
        "conclusions",
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
        提取局限性（Conclusion末尾找局限性信号句）

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

            if any(kw in title for kw in LimitationsRuleD.CONCLUSION_TITLES):
                start = match.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(paper_md)
                content = paper_md[start:end].strip()
                cleaned = clean_markdown_text(content)

                # 获取所有句子
                all_sentences = extract_first_n_sentences(cleaned, n=len(cleaned), method="regex")

                # 跳过"Future Work"等子标题后的内容
                keep_end = len(all_sentences)
                for j, sent in enumerate(all_sentences):
                    sent_lower = sent.lower()
                    if "future work" in sent_lower or "future direction" in sent_lower:
                        keep_end = j
                        break

                # 从后往前找第一个高优先级信号句
                for signal in LimitationsRuleD.LIMITATION_SIGNALS:
                    for j in range(keep_end - 1, -1, -1):
                        sent_lower = all_sentences[j].lower()
                        if signal in sent_lower:
                            # 取信号句+后1句
                            end_idx = min(keep_end, j + 2)
                            selected = all_sentences[j:end_idx]
                            if selected:
                                return " ".join(selected[:max_sentences])

                # 没有找到信号，取section最后N句
                if keep_end >= max_sentences:
                    return " ".join(all_sentences[keep_end - max_sentences:keep_end])
                elif keep_end > 0:
                    return " ".join(all_sentences[:keep_end])

        return None


if __name__ == "__main__":
    test_md = """
# Conclusion
Our method achieves SOTA results on ImageNet. However, it is computationally expensive.
Future work includes improving efficiency.
    """

    result = LimitationsRuleD.extract(test_md)
    print(f"Extracted limitations: {result}")