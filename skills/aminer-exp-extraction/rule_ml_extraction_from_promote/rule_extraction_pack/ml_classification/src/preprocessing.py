"""
文本预处理模块 - Text Preprocessing Module

为不同分类任务设计相应的文本提取策略
Design corresponding text extraction strategies for different classification tasks

主要功能 Main Functions:
- 从论文中提取标题和摘要
- 根据GPT建议的策略提取关键文本块
- 文本标准化和清洗
"""

import re
from typing import Optional, List
from pathlib import Path


class TextPreprocessor:
    """文本预处理器 - Text Preprocessor"""

    def __init__(self):
        """初始化预处理器"""
        pass

    def extract_title(self, paper_md: str) -> str:
        """
        提取论文标题
        Extract paper title

        伪代码 Pseudocode:
        1. 查找第一个一级markdown header (# Title)
           Find first level-1 markdown header (# Title)
        2. 提取标题内容
           Extract title content
        3. 移除开头的井号和空格
           Remove leading # and spaces
        4. 返回标题
           Return title

        参数 Parameters:
            paper_md: 论文markdown文本 - Paper markdown text

        返回 Returns:
            str: 论文标题 - Paper title
        """
        # 伪代码实现 - Pseudocode implementation
        lines = paper_md.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('#'):
                # 移除所有#符号和前后空格
                title = line.lstrip('#').strip()
                return title if title else ""
        return ""

    def extract_abstract(self, paper_md: str) -> str:
        """
        提取论文摘要
        Extract paper abstract

        伪代码 Pseudocode:
        1. 查找Abstract section
           Find Abstract section
        2. 提取Abstract section的内容
           Extract Abstract section content
        3. 移除section标题
           Remove section header
        4. 返回摘要文本
           Return abstract text

        参数 Parameters:
            paper_md: 论文markdown文本 - Paper markdown text

        返回 Returns:
            str: 论文摘要 - Paper abstract
        """
        # 伪代码实现 - Pseudocode implementation
        lines = paper_md.split('\n')
        in_abstract = False
        abstract_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                if in_abstract:
                    break
                continue
            if line.lower().startswith("# abstract"):
                continue
            if in_abstract:
                abstract_lines.append(line)

        return " ".join(abstract_lines)

    def extract_abstract_last_sentences(self, abstract: str, n: int = 2) -> str:
        """
        提取摘要的最后n句话
        Extract last n sentences from abstract

        伪代码 Pseudocode:
        1. 按句号分割文本
           Split text by periods
        2. 过滤空句子
           Filter empty sentences
        3. 取最后n句话
           Take last n sentences
        4. 用句号连接
           Join with periods
        5. 返回结果
           Return result

        参数 Parameters:
            abstract: 论文摘要 - Paper abstract
            n: 要提取的句子数量 - Number of sentences to extract

        返回 Returns:
            str: 最后n句话 - Last n sentences
        """
        # 伪代码实现 - Pseudocode implementation
        if not abstract:
            return ""

        sentences = [s.strip() for s in abstract.split('.') if s.strip()]
        if len(sentences) <= n:
            return abstract

        last_n = sentences[-n:]
        return ". ".join(last_n)

    def extract_experiments_section(self, paper_md: str, max_words: int = 200) -> str:
        """
        提取实验章节的前max_words个词
        Extract first max_words from experiment section

        伪代码 Pseudocode:
        1. 查找Experiments/Results/Evaluation章节
           Find Experiments/Results/Evaluation sections
        2. 提取该section的内容
           Extract content of that section
        3. 按空格分词，取前max_words个
           Split by spaces, take first max_words
        4. 用空格连接
           Join with spaces
        5. 返回结果
           Return result

        参数 Parameters:
            paper_md: 论文markdown文本 - Paper markdown text
            max_words: 最多提取的词数 - Maximum words to extract

        返回 Returns:
            str: 提取的文本 - Extracted text
        """
        # 伪代码实现 - Pseudocode implementation
        section_keywords = ["experiments", "results", "evaluation", "experimental"]

        lines = paper_md.split('\n')
        in_target_section = False
        section_lines = []

        for line in lines:
            line_lower = line.lower()
            if not line:
                if in_target_section:
                    break
                continue
            if any(keyword in line_lower for keyword in section_keywords):
                in_target_section = True
            elif in_target_section:
                section_lines.append(line)

        if not section_lines:
            return ""

        # 合并并提取前max_words个词
        text = " ".join(section_lines)
        words = text.split()[:max_words]
        return " ".join(words)

    def preprocess_for_experiment_type(self, paper_md: str) -> str:
        """
        为experiment_type分类进行文本预处理
        Preprocess text for experiment type classification

        伪代码 Pseudocode:
        1. 提取标题
           Extract title
        2. 提取摘要
           Extract abstract
        3. 提取摘要的最后2句话
           Extract last 2 sentences from abstract
        4. 提取实验章节前200个词
           Extract first 200 words from experiment section
        5. 将这些部分拼接
           Concatenate these parts
        6. 标准化文本（小写、去除标点）
           Normalize text (lowercase, remove punctuation)
        7. 返回结果
           Return result

        参数 Parameters:
            paper_md: 论文markdown文本 - Paper markdown text

        返回 Returns:
            str: 预处理后的文本 - Preprocessed text
        """
        # 伪代码实现 - Pseudocode implementation
        title = self.extract_title(paper_md)
        abstract = self.extract_abstract(paper_md)

        # 提取abstract最后两句
        abstract_last_two = self.extract_abstract_last_sentences(abstract, n=2)

        # 提取实验章节前200词
        experiments_text = self.extract_experiments_section(paper_md, max_words=200)

        # 拼接所有部分
        combined = f"{title} {abstract_last_two} {experiments_text}"

        # 标准化处理
        normalized = combined.lower()
        normalized = re.sub(r'[^\w\s]', ' ', normalized)  # 移除特殊字符
        normalized = re.sub(r'\s+', ' ', normalized)        # 多个空格转一个
        normalized = normalized.strip()

        return normalized

    def preprocess_for_domain(self, paper_md: str) -> str:
        """
        为domain分类进行文本预处理
        Preprocess text for domain classification

        伪代码 Pseudocode:
        1. 提取标题
           Extract title
        2. 提取摘要
           Extract abstract
        3. 对于domain分类，标题通常包含领域关键词
           For domain classification, title often contains domain keywords
        4. 标准化处理
           Normalize text (lowercase, remove punctuation)
        5. 返回结果
           Return result

        参数 Parameters:
            paper_md: 论文markdown文本 - Paper markdown text

        返回 Returns:
            str: 预处理后的文本 - Preprocessed text
        """
        # 伪代码实现 - Pseudocode implementation
        title = self.extract_title(paper_md)
        abstract = self.extract_abstract(paper_md)

        # domain更依赖标题中的领域关键词
        combined = f"{title} {abstract}"

        # 标准化处理
        normalized = combined.lower()
        normalized = re.sub(r'[^\w\s]', ' ', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)
        normalized = normalized.strip()

        return normalized

    def preprocess_for_dataset_type(self, paper_md: str, dataset_description: str) -> str:
        """
        为dataset_type分类进行文本预处理
        Preprocess text for dataset type classification

        伪代码 Pseudocode:
        1. 提取数据集名称
           Extract dataset name
        2. 如果有描述，提取描述文本
           If description exists, extract description text
        3. 标准化处理
           Normalize text (lowercase, remove punctuation)
        4. 返回结果
           Return result

        参数 Parameters:
            paper_md: 论文markdown文本 - Paper markdown text
            dataset_description: 数据集描述 - Dataset description

        返回 Returns:
            str: 预处理后的文本 - Preprocessed text
        """
        # 伪代码实现 - Pseudocode implementation
        if not dataset_description:
            return paper_md[:200]  # 如果没有描述，取论文前200词

        # 标准化处理
        normalized = dataset_description.lower()
        normalized = re.sub(r'[^\w\s]', ' ', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)
        normalized = normalized.strip()

        return normalized

    def load_paper_md(self, paper_id: str, corpus_dir: Path) -> str:
        """
        根据paper_id加载论文md文件
        Load paper md file by paper_id

        伪代码 Pseudocode:
        1. 构建文件路径
           Build file path
        2. 读取文件内容
           Read file content
        3. 返回内容
           Return content

        参数 Parameters:
            paper_id: 论文ID - Paper ID
            corpus_dir: 论文集目录 - Corpus directory

        返回 Returns:
            str: 论文markdown文本 - Paper markdown text
        """
        # 伪代码实现 - Pseudocode implementation
        file_path = corpus_dir / f"{paper_id}.md"

        if not file_path.exists():
            return ""

        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()

        return ""