"""
样本大小提取规则 - Sample Size Extraction Rule

从论文中提取实验样本大小
Extract experiment sample size from papers

主要策略 Main Strategies:
1. 在实验相关sections中搜索样本数量描述
   Search for sample size descriptions in experiment-related sections
2. 使用正则表达式匹配数字 + 关键词
   Use regex to match numbers + keywords
3. 如果找到多个可能的值，选择最合适的
   Choose the most appropriate value if multiple candidates found
"""

import re
from typing import Optional, List, Tuple


class SampleSizeRule:
    """样本大小提取规则 - Sample Size Extraction Rule"""

    # 样本大小相关的关键词 - Keywords related to sample size
    SAMPLE_KEYWORDS = [
        "sample", "samples", "subject", "subjects", "participant", "participants",
        "instance", "instances", "example", "examples", "case", "cases",
        "data point", "data points", "observation", "observations"
    ]

    # 常见的样本大小表达模式 - Common sample size expression patterns
    PATTERNS = [
        # "1234 samples" / "1234 subjects"
        r"(\d{1,6})\s+(?:samples?|subjects?|participants?|instances?|cases?)\b",
        # "sample size: 1234"
        r"sample\s+size\s*[:=]\s*(\d{1,6})",
        # "N = 1234" / "N=1234"
        r"N\s*[=]\s*(\d{1,6})\b",
        # "total of 1234"
        r"(?:total|overall)\s+(?:of\s+)?(\d{1,6})\s+(?:samples?|subjects?)",
        # "dataset consists of 1234"
        r"dataset\s+(?:consists?\s+of|contains?)\s+(\d{1,6})",
        # "we collected 1234"
        r"(?:we|the\s+study)\s+(?:collected|gathered|used)\s+(\d{1,6})\s+(?:samples?|data)",
        # "1234 data points"
        r"(\d{1,6})\s+data\s+points?",
    ]

    # 排除的数字（如年份、页码等） - Numbers to exclude (like years, page numbers)
    EXCLUDED_PATTERNS = [
        r"\b(19|20)\d{2}\b",  # 年份 - Years: 1900-2099
        r"\b\d{1,3}\s*(?:pages?|page)\b",  # 页码 - Page numbers
    ]

    @staticmethod
    def extract(paper_md: str,
                section_filter: bool = True) -> Optional[int]:
        """
        从论文中提取样本大小
        Extract sample size from paper

        伪代码 Pseudocode:
        1. 如果启用section过滤，只在实验相关sections中搜索
           If section filter enabled, search only in experiment-related sections
        2. 使用多个正则模式匹配可能的样本大小
           Use multiple regex patterns to match possible sample sizes
        3. 过滤掉排除的数字（年份、页码等）
           Filter out excluded numbers (years, page numbers, etc.)
        4. 如果找到多个候选值，选择最合适的（最大值或出现频率最高的）
           If multiple candidates found, choose the most appropriate (largest or most frequent)
        5. 返回样本大小，未找到则返回None
           Return sample size, None if not found

        参数 Parameters:
            paper_md: 论文markdown文本 - Paper markdown text
            section_filter: 是否只在实验sections中搜索
                            Whether to search only in experiment sections

        返回 Returns:
            Optional[int]: 样本大小 - Sample size
        """
        # 伪代码实现 - Pseudocode implementation
        target_text = paper_md

        # 1. 可选的section过滤 - Optional section filtering
        # if section_filter:
        #     target_text = SampleSizeRule._filter_experiment_sections(paper_md)

        # 2. 提取所有候选值 - Extract all candidate values
        # candidates = []
        # for pattern in SampleSizeRule.PATTERNS:
        #     matches = re.findall(pattern, target_text, re.IGNORECASE)
        #     candidates.extend([int(match) for match in matches])

        # 3. 过滤排除值 - Filter excluded values
        # filtered_candidates = []
        # for candidate in candidates:
        #     if not SampleSizeRule._is_excluded(candidate, target_text):
        #         filtered_candidates.append(candidate)

        # 4. 选择最佳候选 - Select best candidate
        # if filtered_candidates:
        #     return SampleSizeRule._select_best_candidate(filtered_candidates)

        return None

    @staticmethod
    def _filter_experiment_sections(paper_md: str) -> str:
        """
        过滤出实验相关sections
        Filter out experiment-related sections

        伪代码 Pseudocode:
        1. 识别markdown中的所有section headers
           Identify all section headers in markdown
        2. 选择实验相关的sections（如 "Experiment", "Results", "Setup"）
           Select experiment-related sections (like "Experiment", "Results", "Setup")
        3. 返回合并的实验section内容
           Return merged experiment section content
        """
        # 伪代码实现 - Pseudocode implementation
        # exp_sections = ["experiment", "results", "setup", "methodology", "dataset"]
        # filtered_content = ""
        # for section in exp_sections:
        #     section_content = extract_section_content(paper_md, section)
        #     filtered_content += section_content + "\n"
        # return filtered_content
        return paper_md

    @staticmethod
    def _is_excluded(number: int, context: str) -> bool:
        """
        检查数字是否应该被排除
        Check if number should be excluded

        伪代码 Pseudocode:
        1. 检查数字是否在年份范围内（1900-2099）
           Check if number is in year range (1900-2099)
        2. 检查数字是否出现在页码上下文中
           Check if number appears in page number context
        3. 返回是否应该排除
           Return whether should exclude
        """
        # 伪代码实现 - Pseudocode implementation
        # # 检查年份 - Check years
        # if 1900 <= number <= 2099:
        #     return True
        # # 检查页码上下文 - Check page context
        # page_context = re.search(rf"\b{number}\s*(?:pages?|page)\b", context, re.IGNORECASE)
        # if page_context:
        #     return True
        # return False
        return False

    @staticmethod
    def _select_best_candidate(candidates: List[int]) -> int:
        """
        从多个候选值中选择最佳值
        Select best value from multiple candidates

        伪代码 Pseudocode:
        1. 如果只有一个候选，直接返回
           If only one candidate, return directly
        2. 统计每个候选值的出现频率
           Count frequency of each candidate value
        3. 选择出现频率最高的值
           Choose value with highest frequency
        4. 如果频率相同，选择较大的值（假设较大样本更可能是总样本）
           If frequencies equal, choose larger value (assuming larger sample is more likely total)
        5. 返回最佳候选
           Return best candidate
        """
        # 伪代码实现 - Pseudocode implementation
        # if len(candidates) == 1:
        #     return candidates[0]
        # # 统计频率 - Count frequency
        # from collections import Counter
        # counter = Counter(candidates)
        # # 选择频率最高的 - Choose highest frequency
        # best = counter.most_common(1)[0][0]
        # return best
        return max(candidates) if candidates else None

    @staticmethod
    def extract_all_candidates(paper_md: str) -> List[Tuple[int, str]]:
        """
        提取所有候选样本大小及其上下文
        Extract all candidate sample sizes with their contexts

        伪代码 Pseudocode:
        1. 使用所有模式匹配候选值
           Use all patterns to match candidates
        2. 提取每个匹配的上下文（前后句子）
           Extract context for each match (surrounding sentences)
        3. 返回候选值列表，每个值附带其上下文
           Return candidate list with their contexts

        参数 Parameters:
            paper_md: 论文markdown文本 - Paper markdown text

        返回 Returns:
            List[Tuple[int, str]]: 候选值列表，格式为[(值, 上下文), ...]
                                  Candidate list, format [(value, context), ...]
        """
        # 伪代码实现 - Pseudocode implementation
        # candidates = []
        # for pattern in SampleSizeRule.PATTERNS:
        #     for match in re.finditer(pattern, paper_md, re.IGNORECASE):
        #         value = int(match.group(1))
        #         context = SampleSizeRule._get_context(paper_md, match.start(), match.end())
        #         candidates.append((value, context))
        # return candidates
        return []

    @staticmethod
    def _get_context(text: str, start: int, end: int,
                     window: int = 100) -> str:
        """
        获取匹配位置的上下文
        Get context around match position

        伪代码 Pseudocode:
        1. 计算上下文窗口的起始和结束位置
           Calculate start and end positions of context window
        2. 提取上下文文本
           Extract context text
        3. 返回上下文
           Return context
        """
        # 伪代码实现 - Pseudocode implementation
        # context_start = max(0, start - window)
        # context_end = min(len(text), end + window)
        # return text[context_start:context_end]
        return ""