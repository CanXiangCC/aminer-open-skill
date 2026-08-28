"""
共享工具模块 - Shared Utilities

规则提取实验的基础工具函数
Basic utility functions for rule extraction experiments
"""

from typing import List, Optional
import re


def extract_section_by_keywords(md_text: str, keywords: List[str]) -> Optional[str]:
    """
    根据关键词提取section内容
    Extract section content by keywords

    Args:
        md_text: Markdown文本 - Markdown text
        keywords: 关键词列表（匹配section标题） - List of keywords (match section titles)

    Returns:
        Optional[str]: 提取到的section内容，未找到返回None - Extracted section content, None if not found
    """
    HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
    matches = list(HEADER_RE.finditer(md_text))

    if not matches:
        return None

    # 查找匹配的section - Find matching section
    for i, match in enumerate(matches):
        title = match.group(2).strip().lower()

        # 检查是否匹配关键词 - Check if matches any keyword
        if any(keyword.lower() in title for keyword in keywords):
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(md_text)
            return md_text[start:end].strip()

    return None


def extract_first_n_sentences(text: str, n: int = 3, method: str = "regex") -> List[str]:
    """
    提取前n个句子 - Extract first n sentences

    Args:
        text: 输入文本 - Input text
        n: 句子数量 - Number of sentences
        method: 切分方法: "regex" 或 "nlk" - Split method: "regex" or "nlk"

    Returns:
        List[str]: 句子列表 - List of sentences
    """
    if method == "regex":
        return _split_sentences_regex(text, n)
    elif method == "nlk":
        return _split_sentences_nlkt(text, n)
    else:
        raise ValueError(f"Unknown method: {method}")


def _split_sentences_regex(text: str, n: int) -> List[str]:
    """
    使用正则表达式切分句子 - Split sentences using regex

    处理常见缩写：Dr., Mr., Mrs., Prof., Ph.D., etc.
    Handle common abbreviations: Dr., Mr., Mrs., Prof., Ph.D., etc.
    """
    # 先用占位符保护常见缩写 - First protect common abbreviations with placeholders
    abbreviations = [
        r"Dr\.", r"Mr\.", r"Mrs\.", r"Ms\.", r"Prof\.",
        r"Ph\.D\.", r"Ph\.D", r"M\.D\.", r"B\.S\.",
        r"U\.S\.", r"U\.K\.", r"e\.g\.", r"i\.e\.",
        r"Fig\.", r"Sec\.", r"Eq\.", r"vs\.",
        r"et al\.", r"etc\."
    ]

    protected = text
    for i, abbr in enumerate(abbreviations):
        protected = re.sub(abbr, f"@@ABBR{i}@@@@", protected, flags=re.IGNORECASE)

    # 句子分隔符 - Sentence delimiter
    sentences = re.split(r"(?<=[.!?])\s+", protected)

    # 恢复缩写 - Restore abbreviations
    sentences = [re.sub(r"@@ABBR\d+@@@@", ".", s) for s in sentences]

    # 清理并返回 - Clean and return
    sentences = [s.strip() for s in sentences if s.strip()]
    return sentences[:n]


def _split_sentences_nlkt(text: str, n: int) -> List[str]:
    """
    使用NLTK切分句子 - Split sentences using NLTK (if available)
    """
    try:
        import nltk
        nltk.data.find('tokenizers/punkt')
    except (ImportError, LookupError):
        # NLTK不可用，回退到正则 - NLTK not available, fallback to regex
        return _split_sentences_regex(text, n)

    sentences = nltk.sent_tokenize(text)
    return [s.strip() for s in sentences[:n] if s.strip()]


def clean_markdown_text(text: str) -> str:
    """
    完整清理Markdown文本 - Complete markdown text cleaning

    清理内容:
    - LaTeX数学公式: $$...$$, $...$
    - 脚注: ^1, [^1]
    - 引用: [1], [1-3]
    - 链接: [text](url) -> text
    - 图片: ![alt](url)
    - 表格: HTML表格
    - 代码块: ```...```

    Args:
        text: 原始Markdown文本 - Original Markdown text

    Returns:
        str: 清理后的文本 - Cleaned text
    """
    if not text:
        return ""

    cleaned = text

    # 移除显示数学公式 - Remove display math: $$...$$
    cleaned = re.sub(r"\$\$.*?\$\$", "[MATH]", cleaned, flags=re.DOTALL)

    # 移除行内数学公式 - Remove inline math: $...$
    cleaned = re.sub(r"(?<!\$)\$(?!\$).*?\$(?!\$)", "[MATH]", cleaned)

    # 移除脚注 - Remove footnotes
    cleaned = re.sub(r"\^\d+", "", cleaned)  # ^1, ^2
    cleaned = re.sub(r"\[\^\d+\]", "", cleaned)  # [^1], [^2]

    # 移除引用 - Remove citations
    cleaned = re.sub(r"\[\d+(?:-\d+)?\]", "", cleaned)  # [1], [1-3]

    # 移除链接，保留文本 - Remove links, keep text
    cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cleaned)

    # 移除图片 - Remove images
    cleaned = re.sub(r"!\[([^\]]*)\]\([^\)]+\)", "", cleaned)

    # 移除HTML表格 - Remove HTML tables
    cleaned = re.sub(r"<table\b[^>]*>.*?</table>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)

    # 移除代码块 - Remove code blocks
    cleaned = re.sub(r"```.*?```", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"`[^`]+`", "", cleaned)

    # 移除多余空白 - Remove extra whitespace
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = cleaned.strip()

    return cleaned