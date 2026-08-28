"""
规则提取器 - Rule Extractor

负责调用各规则模块提取可规则化的字段
Responsible for calling various rule modules to extract rule-based fields

主要功能 Main Functions:
- 从论文markdown中提取结构化字段 - Extract structured fields from paper markdown
- 提供统一的规则提取接口 - Provide unified rule extraction interface
- 管理各规则模块的执行顺序 - Manage execution order of rule modules
"""

from typing import Dict, Any
import re


class RuleExtractor:
    """规则提取器 - Rule Extractor"""

    def __init__(self):
        """
        初始化规则提取器
        Initialize rule extractor
        """
        # 加载所有规则模块 - Load all rule modules
        # self.rules = self._load_rules()
        pass

    def extract(self, paper_md: str, paper_metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        从论文文本中提取结构化字段
        Extract structured fields from paper text

        参数 Parameters:
            paper_md: 论文的markdown文本 - Paper markdown text
            paper_metadata: 论文元数据（文件名、路径等） - Paper metadata (filename, path, etc.)

        返回 Returns:
            Dict[str, Any]: 提取的字段字典 - Extracted fields dictionary

        示例 Example:
            {
                "paper_id": "5b1643ba8fbcbf6e5a9bc884",
                "sample_size": 792,
                "domain": "computer_science",
                "experiment_type": "benchmark"
            }
        """
        result = {}

        # 1. 提取paper_id - Extract paper_id
        # result["paper_id"] = PaperIDRule.extract(paper_md, paper_metadata)

        # 2. 提取sample_size - Extract sample_size
        # result["sample_size"] = SampleSizeRule.extract(paper_md)

        # 3. 提取domain - Extract domain
        # result["domain"] = DomainRule.extract(paper_md)

        # 4. 提取experiment_type - Extract experiment_type
        # result["experiment_type"] = ExperimentTypeRule.extract(paper_md)

        # 5. 可扩展更多规则提取 - Extensible for more rule extractions
        # result["dataset_names"] = DatasetNameRule.extract(paper_md)

        return result

    def _load_rules(self):
        """
        加载所有可用的规则模块
        Load all available rule modules

        返回 Returns:
            list: 规则模块列表 - List of rule modules
        """
        rules = []
        # 动态加载rules目录下的所有规则模块 - Dynamically load all rule modules in rules directory
        # for rule_file in glob.glob("rules/*.py"):
        #     module = import_rule_module(rule_file)
        #     rules.append(module)
        return rules

    def get_supported_fields(self) -> list:
        """
        获取所有支持规则提取的字段
        Get all fields supported by rule extraction

        返回 Returns:
            list: 支持的字段列表 - List of supported fields
        """
        return [
            "paper_id",
            "sample_size",
            "domain",
            "experiment_type",
            # "dataset_names",
            # "metrics_names",
        ]


class PaperIDRule:
    """论文ID提取规则 - Paper ID Extraction Rule"""

    @staticmethod
    def extract(paper_md: str, paper_metadata: Dict[str, Any] = None) -> str:
        """
        从元数据或文件名中提取论文ID
        Extract paper ID from metadata or filename

        伪代码 Pseudocode:
        1. 如果提供了paper_metadata，尝试从中提取paper_id字段
           If paper_metadata is provided, try to extract paper_id field
        2. 否则，从文件路径中解析paper_id
           Otherwise, parse paper_id from file path
        3. 返回提取的paper_id
           Return extracted paper_id

        参数 Parameters:
            paper_md: 论文markdown文本 - Paper markdown text
            paper_metadata: 论文元数据 - Paper metadata

        返回 Returns:
            str: 论文ID - Paper ID
        """
        # 伪代码实现 - Pseudocode implementation
        if paper_metadata and "paper_id" in paper_metadata:
            return paper_metadata["paper_id"]
        # 否则从路径解析 - Otherwise parse from path
        # return extract_id_from_path(paper_metadata.get("path"))
        return ""


class SampleSizeRule:
    """样本大小提取规则 - Sample Size Extraction Rule"""

    @staticmethod
    def extract(paper_md: str) -> int:
        """
        从论文中提取样本大小
        Extract sample size from paper

        伪代码 Pseudocode:
        1. 在实验相关sections中搜索样本数量描述
           Search for sample size descriptions in experiment-related sections
        2. 使用正则表达式匹配数字 + 关键词（如 "samples", "subjects", "participants"）
           Use regex to match numbers + keywords (like "samples", "subjects", "participants")
        3. 如果找到多个可能的值，选择最大的或最相关的
           If multiple possible values found, choose the largest or most relevant
        4. 返回提取的样本大小，未找到则返回None
           Return extracted sample size, None if not found

        参数 Parameters:
            paper_md: 论文markdown文本 - Paper markdown text

        返回 Returns:
            int: 样本大小 - Sample size
        """
        # 伪代码实现 - Pseudocode implementation
        # patterns = [
        #     r"(\d+)\s+(?:samples?|subjects?|participants?)",
        #     r"sample\s+size\s*:?\s*(\d+)",
        #     r"N\s*=\s*(\d+)",
        # ]
        # for pattern in patterns:
        #     match = re.search(pattern, paper_md)
        #     if match:
        #         return int(match.group(1))
        return None


class DomainRule:
    """领域提取规则 - Domain Extraction Rule"""

    @staticmethod
    def extract(paper_md: str) -> str:
        """
        从论文中提取研究领域
        Extract research domain from paper

        伪代码 Pseudocode:
        1. 检查论文标题、摘要、关键词中的领域信息
           Check domain information in title, abstract, keywords
        2. 匹配预定义的领域列表（computer_science, medicine, physics等）
           Match against predefined domain list (computer_science, medicine, physics, etc.)
        3. 返回匹配的领域，默认为"computer_science"
           Return matched domain, default to "computer_science"

        参数 Parameters:
            paper_md: 论文markdown文本 - Paper markdown text

        返回 Returns:
            str: 研究领域 - Research domain
        """
        # 伪代码实现 - Pseudocode implementation
        # domains = ["computer_science", "medicine", "physics", "biology"]
        # for domain in domains:
        #     if domain in paper_md.lower():
        #         return domain
        return "computer_science"


class ExperimentTypeRule:
    """实验类型提取规则 - Experiment Type Extraction Rule"""

    @staticmethod
    def extract(paper_md: str) -> str:
        """
        从论文中提取实验类型
        Extract experiment type from paper

        伪代码 Pseudocode:
        1. 检查实验section中的关键词
           Check keywords in experiment section
        2. 匹配预定义的实验类型（benchmark, comparison, human_study, case_study等）
           Match against predefined experiment types (benchmark, comparison, human_study, case_study, etc.)
        3. 返回匹配的实验类型，默认为"comparison"
           Return matched experiment type, default to "comparison"

        参数 Parameters:
            paper_md: 论文markdown文本 - Paper markdown text

        返回 Returns:
            str: 实验类型 - Experiment type
        """
        # 伪代码实现 - Pseudocode implementation
        # exp_types = ["benchmark", "comparison", "human_study", "case_study", "ablation"]
        # for exp_type in exp_types:
        #     if exp_type in paper_md.lower():
        #         return exp_type
        return "comparison"