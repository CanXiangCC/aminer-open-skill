"""
实验类型提取规则 - Experiment Type Extraction Rule

从论文中提取实验类型
Extract experiment type from papers

主要策略 Main Strategies:
1. 检查实验section中的关键词
   Check keywords in experiment section
2. 匹配预定义的实验类型特征
   Match predefined experiment type characteristics
3. 根据实验方法和目标进行分类
   Classify based on experiment methods and goals
"""

import re
from typing import Optional, Dict, List, Tuple


class ExperimentTypeRule:
    """实验类型提取规则 - Experiment Type Extraction Rule"""

    # 预定义的实验类型及其特征
    # Predefined experiment types and their characteristics
    EXPERIMENT_TYPES = {
        "benchmark": {
            "keywords": [
                "benchmark", "benchmarking", "evaluation", "evaluate", "measure",
                "performance", "compare", "comparison", "standard", "dataset",
                "test set", "leaderboard", "state-of-the-art", "SOTA", "baseline"
            ],
            "phrases": [
                "we evaluate", "we benchmark", "performance comparison",
                "state-of-the-art", "baseline comparison", "evaluation on"
            ],
            "weight": 1.0,
            "aliases": ["evaluation", "comparison"]
        },
        "comparison": {
            "keywords": [
                "compare", "comparison", "versus", "vs", "compared to",
                "against", "different methods", "alternative", "approach"
            ],
            "phrases": [
                "we compare", "compared with", "versus", "different approaches",
                "alternative methods", "comparative study"
            ],
            "weight": 1.0,
            "aliases": ["comparative", "versus"]
        },
        "human_study": {
            "keywords": [
                "human", "participant", "user study", "human evaluation",
                "crowdsourcing", "user", "annotator", "human subject",
                "real user", "user feedback", "human judgment"
            ],
            "phrases": [
                "human evaluation", "user study", "human subjects",
                "crowdsourcing", "human judgment", "real users", "user feedback"
            ],
            "weight": 1.0,
            "aliases": ["user study", "human evaluation"]
        },
        "case_study": {
            "keywords": [
                "case study", "case analysis", "specific example", "example",
                "scenario", "use case", "demonstration", "real-world"
            ],
            "phrases": [
                "case study", "as a case study", "we demonstrate",
                "as an example", "in a real-world scenario", "use case"
            ],
            "weight": 1.0,
            "aliases": ["demonstration", "example"]
        },
        "ablation": {
            "keywords": [
                "ablation", "ablation study", "component", "module", "variant",
                "configuration", "setting", "variant analysis", "component analysis"
            ],
            "phrases": [
                "ablation study", "we conduct ablation", "component analysis",
                "effect of", "impact of", "ablation experiment"
            ],
            "weight": 1.0,
            "aliases": ["component analysis", "variant analysis"]
        },
        "robustness": {
            "keywords": [
                "robust", "robustness", "noise", "adversarial", "perturbation",
                "resistance", "stability", "stress test", "adversarial attack"
            ],
            "phrases": [
                "robustness analysis", "robust to", "resistant to",
                "adversarial", "noise injection", "stress test"
            ],
            "weight": 1.0,
            "aliases": ["stability", "adversarial"]
        },
        "efficiency": {
            "keywords": [
                "efficiency", "efficient", "speed", "latency", "runtime",
                "time complexity", "computational cost", "memory", "resource",
                "scalability", "throughput"
            ],
            "phrases": [
                "efficiency evaluation", "runtime analysis", "computational cost",
                "memory usage", "scalability analysis", "throughput"
            ],
            "weight": 1.0,
            "aliases": ["performance", "speed", "scalability"]
        },
        "statistical": {
            "keywords": [
                "statistical", "statistics", "hypothesis", "significance",
                "p-value", "confidence interval", "regression", "correlation",
                "statistical analysis", "empirical"
            ],
            "phrases": [
                "statistical analysis", "statistical significance", "hypothesis test",
                "confidence interval", "p-value", "regression analysis"
            ],
            "weight": 1.0,
            "aliases": ["empirical", "hypothesis test"]
        },
        "simulation": {
            "keywords": [
                "simulation", "simulator", "synthetic", "synthesized", "generated",
                "artificial", "mock", "virtual", "environment"
            ],
            "phrases": [
                "simulation study", "synthetic data", "simulated environment",
                "virtual experiment", "mock scenario"
            ],
            "weight": 1.0,
            "aliases": ["synthetic", "virtual"]
        }
    }

    @staticmethod
    def extract(paper_md: str,
                use_experiment_sections: bool = True,
                min_score: float = 0.05) -> Optional[str]:
        """
        从论文中提取实验类型
        Extract experiment type from paper

        伪代码 Pseudocode:
        1. 如果启用实验section过滤，只在实验相关sections中搜索
           If experiment section filter enabled, search only in experiment-related sections
        2. 对每种实验类型进行关键词和短语匹配
           Perform keyword and phrase matching for each experiment type
        3. 计算每种实验类型的得分
           Calculate score for each experiment type
        4. 选择得分最高且超过最小得分的类型
           Choose type with highest score above minimum
        5. 返回实验类型，未找到则返回None
           Return experiment type, None if not found

        参数 Parameters:
            paper_md: 论文markdown文本 - Paper markdown text
            use_experiment_sections: 是否只在实验sections中搜索
                                      Whether to search only in experiment sections
            min_score: 最小得分阈值 - Minimum score threshold

        返回 Returns:
            Optional[str]: 实验类型 - Experiment type
        """
        # 伪代码实现 - Pseudocode implementation
        # 1. 可选的section过滤 - Optional section filtering
        # target_text = paper_md
        # if use_experiment_sections:
        #     target_text = ExperimentTypeRule._filter_experiment_sections(paper_md)

        # 2. 对每种实验类型计算得分 - Calculate score for each experiment type
        # type_scores = {}
        # for exp_type, type_info in ExperimentTypeRule.EXPERIMENT_TYPES.items():
        #     score = ExperimentTypeRule._calculate_type_score(
        #         target_text,
        #         type_info["keywords"],
        #         type_info["phrases"]
        #     )
        #     type_scores[exp_type] = score * type_info["weight"]

        # 3. 选择最佳类型 - Select best type
        # if type_scores:
        #     best_type = max(type_scores.items(), key=lambda x: x[1])
        #     if best_type[1] >= min_score:
        #         return best_type[0]

        return "comparison"  # 默认值 - Default value

    @staticmethod
    def _filter_experiment_sections(paper_md: str) -> str:
        """
        过滤出实验相关sections
        Filter out experiment-related sections

        伪代码 Pseudocode:
        1. 识别markdown中的所有section headers
           Identify all section headers in markdown
        2. 选择实验相关的sections
           Select experiment-related sections
        3. 返回合并的实验section内容
           Return merged experiment section content
        """
        # 伪代码实现 - Pseudocode implementation
        # exp_sections = [
        #     "experiment", "experiments", "experimental", "result", "results",
        #     "evaluation", "analysis", "methodology", "setup", "implementation"
        # ]
        # filtered_content = ""
        # for section in exp_sections:
        #     section_content = extract_section_content(paper_md, section)
        #     filtered_content += section_content + "\n"
        # return filtered_content
        return paper_md

    @staticmethod
    def _calculate_type_score(text: str,
                              keywords: List[str],
                              phrases: List[str]) -> float:
        """
        计算实验类型得分
        Calculate experiment type score

        伪代码 Pseudocode:
        1. 统计关键词在文本中的出现频率（不区分大小写）
           Count frequency of keywords in text (case-insensitive)
        2. 统计短语在文本中的出现频率（不区分大小写）
           Count frequency of phrases in text (case-insensitive)
        3. 短语匹配给予2倍权重
           Give 2x weight to phrase matches
        4. 归一化得分（除以文本长度）
           Normalize score (divide by text length)
        5. 返回最终得分
           Return final score
        """
        # 伪代码实现 - Pseudocode implementation
        # total_score = 0.0
        # text_lower = text.lower()

        # # 关键词匹配 - Keyword matching
        # for keyword in keywords:
        #     keyword_lower = keyword.lower()
        #     keyword_count = text_lower.count(keyword_lower)
        #     total_score += keyword_count

        # # 短语匹配（2倍权重） - Phrase matching (2x weight)
        # for phrase in phrases:
        #     phrase_lower = phrase.lower()
        #     phrase_count = text_lower.count(phrase_lower)
        #     total_score += phrase_count * 2

        # # 归一化 - Normalize
        # normalized_score = total_score / (len(text) + 1)
        # return normalized_score
        return 0.0

    @staticmethod
    def extract_all_types(paper_md: str, top_n: int = 3) -> List[Tuple[str, float]]:
        """
        提取所有可能的实验类型及其得分
        Extract all possible experiment types with their scores

        伪代码 Pseudocode:
        1. 对每种实验类型计算得分
           Calculate score for each experiment type
        2. 按得分降序排序
           Sort by score in descending order
        3. 返回前N个实验类型
           Return top N experiment types

        参数 Parameters:
            paper_md: 论文markdown文本 - Paper markdown text
            top_n: 返回前几个实验类型 - Return top N experiment types

        返回 Returns:
            List[Tuple[str, float]]: 实验类型得分列表，格式为[(类型, 得分), ...]
                                     Experiment type score list, format [(type, score), ...]
        """
        # 伪代码实现 - Pseudocode implementation
        # type_scores = {}
        # for exp_type, type_info in ExperimentTypeRule.EXPERIMENT_TYPES.items():
        #     score = ExperimentTypeRule._calculate_type_score(
        #         paper_md,
        #         type_info["keywords"],
        #         type_info["phrases"]
        #     )
        #     type_scores[exp_type] = score * type_info["weight"]

        # # 排序并返回前N个 - Sort and return top N
        # sorted_types = sorted(
        #     type_scores.items(),
        #     key=lambda x: x[1],
        #     reverse=True
        # )
        # return sorted_types[:top_n]
        return []

    @staticmethod
    def detect_hybrid_types(paper_md: str) -> List[str]:
        """
        检测是否为混合类型的实验
        Detect if experiment has hybrid types

        伪代码 Pseudocode:
        1. 提取所有实验类型及其得分
           Extract all experiment types with their scores
        2. 检查是否有多个类型得分超过阈值
           Check if multiple types have scores above threshold
        3. 如果有，返回这些类型的列表
           If yes, return list of these types
        4. 否则返回空列表
           Otherwise return empty list

        参数 Parameters:
            paper_md: 论文markdown文本 - Paper markdown text

        返回 Returns:
            List[str]: 混合实验类型列表 - Hybrid experiment type list
        """
        # 伪代码实现 - Pseudocode implementation
        # all_types = ExperimentTypeRule.extract_all_types(paper_md, top_n=5)
        # threshold = 0.05  # 最小得分阈值 - Minimum score threshold
        # hybrid_types = [exp_type for exp_type, score in all_types if score >= threshold]
        # return hybrid_types if len(hybrid_types) > 1 else []
        return []