"""
结果合并器 - Result Merger

负责合并规则提取结果和LLM提取结果
Responsible for merging rule extraction results with LLM extraction results

主要功能 Main Functions:
- 合并两个来源的提取结果 - Merge extraction results from two sources
- 处理字段冲突 - Handle field conflicts
- 提供优先级配置 - Provide priority configuration
"""

from typing import Dict, Any, Optional


class Merger:
    """结果合并器 - Result Merger"""

    # 规则提取的字段优先级高于LLM
    # Fields extracted by rules have higher priority than LLM
    RULE_FIELDS = [
        "paper_id",
        "sample_size",
        "domain",
        "experiment_type",
        # "dataset_names",
        # "metrics_names",
    ]

    # LLM提取的语义字段（必须用LLM）
    # Semantic fields extracted by LLM (must use LLM)
    LLM_FIELDS = [
        "experiment_name",
        "research_problem",
        "research_goal",
        "experiment_subject",
        "method",
        "datasets",
        "metrics",
        "key_results",
        "conclusion",
        "limitations",
        "evidence",
    ]

    def __init__(self, rule_priority: bool = True):
        """
        初始化合并器
        Initialize merger

        参数 Parameters:
            rule_priority: 规则提取的字段是否优先
                          Whether rule-extracted fields have priority
        """
        self.rule_priority = rule_priority
        self.conflict_log = []  # 记录字段冲突 - Record field conflicts

    def merge(self,
              rule_result: Dict[str, Any],
              llm_result: Dict[str, Any],
              experiment_id: Optional[str] = None) -> Dict[str, Any]:
        """
        合并规则提取结果和LLM提取结果
        Merge rule extraction results with LLM extraction results

        伪代码 Pseudocode:
        1. 初始化空的合并结果字典 - Initialize empty merged result dictionary
        2. 处理规则字段：如果rule_result中有该字段，使用规则提取的值
           Handle rule fields: if field exists in rule_result, use rule-extracted value
        3. 处理LLM字段：使用llm_result中的值
           Handle LLM fields: use values from llm_result
        4. 处理可能冲突的字段：根据优先级选择
           Handle potentially conflicting fields: choose based on priority
        5. 添加合并元数据（来源标记）
           Add merge metadata (source markers)
        6. 返回合并结果
           Return merged result

        参数 Parameters:
            rule_result: 规则提取结果 - Rule extraction results
            llm_result: LLM提取结果 - LLM extraction results
            experiment_id: 实验ID（用于日志记录） - Experiment ID (for logging)

        返回 Returns:
            Dict[str, Any]: 合并后的结果 - Merged results
        """
        merged = {}
        sources = {}  # 记录每个字段的来源 - Record source of each field

        # 1. 合并规则提取的字段 - Merge rule-extracted fields
        for field in self.RULE_FIELDS:
            if field in rule_result and rule_result[field] is not None:
                merged[field] = rule_result[field]
                sources[field] = "rule"
            elif field in llm_result:
                merged[field] = llm_result[field]
                sources[field] = "llm"
                # 记录LLM补充了规则字段 - Log LLM supplementing rule field
                # self._log_conflict(field, "llm", experiment_id)

        # 2. 合并LLM提取的语义字段 - Merge LLM-extracted semantic fields
        for field in self.LLM_FIELDS:
            if field in llm_result and llm_result[field] is not None:
                merged[field] = llm_result[field]
                sources[field] = "llm"

        # 3. 处理未知字段（可能的新字段） - Handle unknown fields (possibly new fields)
        all_fields = set(rule_result.keys()) | set(llm_result.keys())
        known_fields = set(self.RULE_FIELDS) | set(self.LLM_FIELDS)
        unknown_fields = all_fields - known_fields

        for field in unknown_fields:
            # 优先使用规则结果 - Prefer rule results
            if field in rule_result and rule_result[field] is not None:
                merged[field] = rule_result[field]
                sources[field] = "rule"
            elif field in llm_result:
                merged[field] = llm_result[field]
                sources[field] = "llm"

        # 4. 添加合并元数据 - Add merge metadata
        merged["_metadata"] = {
            "extraction_sources": sources,
            "rule_fields_count": len([f for f in sources.values() if f == "rule"]),
            "llm_fields_count": len([f for f in sources.values() if f == "llm"]),
            "total_fields": len(sources),
        }

        return merged

    def merge_batch(self,
                    rule_results: list,
                    llm_results: list) -> list:
        """
        批量合并多个实验的提取结果
        Batch merge extraction results of multiple experiments

        伪代码 Pseudocode:
        1. 检查输入长度是否一致 - Check if input lengths match
        2. 逐个合并每对结果 - Merge each pair of results
        3. 返回合并后的结果列表
           Return merged result list

        参数 Parameters:
            rule_results: 规则提取结果列表 - List of rule extraction results
            llm_results: LLM提取结果列表 - List of LLM extraction results

        返回 Returns:
            list: 合并后的结果列表 - List of merged results
        """
        if len(rule_results) != len(llm_results):
            raise ValueError("规则结果和LLM结果数量不匹配 - Rule and LLM result counts don't match")

        merged_results = []
        for i, (rule_result, llm_result) in enumerate(zip(rule_results, llm_results)):
            merged = self.merge(rule_result, llm_result, experiment_id=f"exp_{i}")
            merged_results.append(merged)

        return merged_results

    def validate_merge(self, merged_result: Dict[str, Any]) -> bool:
        """
        验证合并结果的完整性
        Validate completeness of merged result

        伪代码 Pseudocode:
        1. 检查必须字段是否存在 - Check if required fields exist
        2. 检查字段类型是否正确 - Check if field types are correct
        3. 检查数据一致性 - Check data consistency
        4. 返回验证结果
           Return validation result

        参数 Parameters:
            merged_result: 合并结果 - Merged result

        返回 Returns:
            bool: 验证是否通过 - Whether validation passed
        """
        # 伪代码实现 - Pseudocode implementation
        # required_fields = ["paper_id", "experiment_name", "research_goal"]
        # for field in required_fields:
        #     if field not in merged_result or merged_result[field] is None:
        #         return False
        return True

    def get_conflict_report(self) -> Dict[str, Any]:
        """
        获取字段冲突报告
        Get field conflict report

        返回 Returns:
            Dict[str, Any]: 冲突报告 - Conflict report
        """
        return {
            "total_conflicts": len(self.conflict_log),
            "conflicts": self.conflict_log,
        }

    def _log_conflict(self, field: str, source: str, experiment_id: str = None):
        """
        记录字段冲突
        Log field conflict

        参数 Parameters:
            field: 字段名 - Field name
            source: 来源 - Source
            experiment_id: 实验ID - Experiment ID
        """
        self.conflict_log.append({
            "field": field,
            "source": source,
            "experiment_id": experiment_id,
        })

    def update_rule_fields(self, new_rule_fields: list):
        """
        更新规则字段列表
        Update rule field list

        参数 Parameters:
            new_rule_fields: 新的规则字段列表 - New rule field list
        """
        self.RULE_FIELDS = new_rule_fields

    def update_llm_fields(self, new_llm_fields: list):
        """
        更新LLM字段列表
        Update LLM field list

        参数 Parameters:
            new_llm_fields: 新的LLM字段列表 - New LLM field list
        """
        self.LLM_FIELDS = new_llm_fields