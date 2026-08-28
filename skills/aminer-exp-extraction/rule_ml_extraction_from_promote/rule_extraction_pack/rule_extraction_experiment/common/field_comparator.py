"""
通用字段对比器 - Universal Field Comparator

支持不同类型字段的对比
Supports comparison of different field types

主要功能 Main Functions:
- 字符串对比 - String comparison
- 数值对比 - Numeric comparison
- 列表对比 - List comparison
- 字典对比 - Dictionary comparison
"""

from typing import Any, Dict, List, Union
from enum import Enum
import difflib


class ComparisonStatus(Enum):
    """对比状态枚举 - Comparison Status Enum"""
    EXACT_MATCH = "exact_match"           # 精确匹配 - Exact match
    PARTIAL_MATCH = "partial_match"       # 部分匹配 - Partial match
    MISMATCH = "mismatch"                 # 不匹配 - Mismatch
    MISSING = "missing"                   # 缺失 - Missing
    ERROR = "error"                       # 错误 - Error


class FieldComparator:
    """
    字段对比器 - Field Comparator

    支持的字段类型 Supported field types:
    - str: 字符串对比 - String comparison
    - int/float: 数值对比 - Numeric comparison
    - list: 列表对比 - List comparison
    - dict: 字典对比 - Dictionary comparison
    - bool: 布尔对比 - Boolean comparison
    - null: 空值对比 - Null comparison
    """

    @staticmethod
    def compare(gold_value: Any, rule_value: Any, field_type: str) -> Dict[str, Any]:
        """
        对比两个字段值
        Compare two field values

        伪代码 Pseudocode:
        1. 检查规则值是否缺失
           Check if rule value is missing
        2. 根据字段类型选择对应的对比方法
           Select corresponding comparison method based on field type
        3. 执行对比
           Perform comparison
        4. 计算相似度（如果适用）
           Calculate similarity (if applicable)
        5. 返回对比结果
           Return comparison result

        参数 Parameters:
            gold_value: gold标准值 - Gold standard value
            rule_value: 规则提取值 - Rule extracted value
            field_type: 字段类型 - Field type

        返回 Returns:
            Dict[str, Any]: {
                "status": "exact_match" | "partial_match" | "mismatch" | "missing" | "error",
                "reason": str,
                "similarity": float,
                "details": dict
            }
        """
        # 伪代码实现 - Pseudocode implementation
        # result = {
        #     "status": ComparisonStatus.ERROR,
        #     "reason": "",
        #     "similarity": 0.0,
        #     "details": {}
        # }
        #
        # # 检查缺失 - Check missing
        # if rule_value is None:
        #     result["status"] = ComparisonStatus.MISSING
        #     result["reason"] = "Rule extraction returned None"
        #     return result
        #
        # # 根据类型对比 - Compare by type
        # try:
        #     if field_type == "str":
        #         result.update(FieldComparator.compare_strings(gold_value, rule_value))
        #     elif field_type == "int":
        #         result.update(FieldComparator.compare_integers(gold_value, rule_value))
        #     elif field_type == "float":
        #         result.update(FieldComparator.compare_floats(gold_value, rule_value))
        #     elif field_type == "list":
        #         result.update(FieldComparator.compare_lists(gold_value, rule_value))
        #     elif field_type == "dict":
        #         result.update(FieldComparator.compare_dicts(gold_value, rule_value))
        #     elif field_type == "bool":
        #         result.update(FieldComparator.compare_booleans(gold_value, rule_value))
        #     else:
        #         result["status"] = ComparisonStatus.ERROR
        #         result["reason"] = f"Unsupported field type: {field_type}"
        # except Exception as e:
        #     result["status"] = ComparisonStatus.ERROR
        #     result["reason"] = f"Comparison error: {str(e)}"
        #
        # return result
        return {}

    @staticmethod
    def compare_strings(gold: str, rule: str, fuzzy: bool = True) -> Dict[str, Any]:
        """
        字符串对比
        String comparison

        支持精确匹配、大小写不敏感、模糊匹配
        Supports exact match, case-insensitive match, fuzzy match

        伪代码 Pseudocode:
        1. 检查gold值是否为空
           Check if gold value is empty
        2. 尝试精确匹配
           Try exact match
        3. 尝试大小写不敏感匹配
           Try case-insensitive match
        4. 如果启用模糊匹配，计算字符串相似度
           If fuzzy matching enabled, calculate string similarity
        5. 根据相似度确定匹配状态
           Determine match status based on similarity
        6. 返回对比结果
           Return comparison result

        参数 Parameters:
            gold: gold标准值 - Gold standard value
            rule: 规则提取值 - Rule extracted value
            fuzzy: 是否启用模糊匹配 - Whether to enable fuzzy matching

        返回 Returns:
            Dict[str, Any]: 对比结果 - Comparison result
        """
        # 伪代码实现 - Pseudocode implementation
        # result = {
        #     "status": ComparisonStatus.MISMATCH,
        #     "reason": "",
        #     "similarity": 0.0,
        #     "details": {}
        # }
        #
        # # 处理gold为空的情况 - Handle gold is None case
        # if gold is None:
        #     if rule is None or rule == "":
        #         result["status"] = ComparisonStatus.EXACT_MATCH
        #         result["reason"] = "Both values are None/empty"
        #     else:
        #         result["status"] = ComparisonStatus.MISMATCH
        #         result["reason"] = "Gold is None but rule has value"
        #     return result
        #
        # # 精确匹配 - Exact match
        # if gold == rule:
        #     result["status"] = ComparisonStatus.EXACT_MATCH
        #     result["reason"] = "Exact match"
        #     result["similarity"] = 1.0
        #     return result
        #
        # # 大小写不敏感匹配 - Case-insensitive match
        # if gold.lower() == rule.lower():
        #     result["status"] = ComparisonStatus.EXACT_MATCH
        #     result["reason"] = "Case-insensitive match"
        #     result["similarity"] = 1.0
        #     return result
        #
        # # 模糊匹配 - Fuzzy match
        # if fuzzy:
        #     # 计算相似度 - Calculate similarity
        #     similarity = difflib.SequenceMatcher(None, gold.lower(), rule.lower()).ratio()
        #     result["similarity"] = similarity
        #
        #     if similarity >= 0.9:
        #         result["status"] = ComparisonStatus.PARTIAL_MATCH
        #         result["reason"] = f"High similarity ({similarity:.2f})"
        #     elif similarity >= 0.7:
        #         result["status"] = ComparisonStatus.PARTIAL_MATCH
        #         result["reason"] = f"Medium similarity ({similarity:.2f})"
        #     else:
        #         result["status"] = ComparisonStatus.MISMATCH
        #         result["reason"] = f"Low similarity ({similarity:.2f})"
        # else:
        #     result["status"] = ComparisonStatus.MISMATCH
        #     result["reason"] = "Values don't match"
        #
        # result["details"] = {
        #     "gold_length": len(gold),
        #     "rule_length": len(rule),
        #     "length_diff": abs(len(gold) - len(rule))
        # }
        #
        # return result
        return {}

    @staticmethod
    def compare_integers(gold: int, rule: int, tolerance: int = 0) -> Dict[str, Any]:
        """
        整数对比
        Integer comparison

        支持精确匹配、容差匹配
        Supports exact match, tolerance match

        伪代码 Pseudocode:
        1. 检查gold值是否为空
           Check if gold value is empty
        2. 尝试精确匹配
           Try exact match
        3. 如果设置容差，检查是否在容差范围内
           If tolerance set, check if within tolerance range
        4. 计算差异百分比（如果gold不为0）
           Calculate difference percentage (if gold is not 0)
        5. 返回对比结果
           Return comparison result

        参数 Parameters:
            gold: gold标准值 - Gold standard value
            rule: 规则提取值 - Rule extracted value
            tolerance: 容差值 - Tolerance value

        返回 Returns:
            Dict[str, Any]: 对比结果 - Comparison result
        """
        # 伪代码实现 - Pseudocode implementation
        # result = {
        #     "status": ComparisonStatus.MISMATCH,
        #     "reason": "",
        #     "similarity": 0.0,
        #     "details": {}
        # }
        #
        # # 处理gold为空的情况 - Handle gold is None case
        # if gold is None:
        #     if rule is None:
        #         result["status"] = ComparisonStatus.EXACT_MATCH
        #         result["reason"] = "Both values are None"
        #     else:
        #         result["status"] = ComparisonStatus.MISMATCH
        #         result["reason"] = "Gold is None but rule has value"
        #     return result
        #
        # # 类型转换处理 - Type conversion handling
        # try:
        #     gold_int = int(gold) if gold is not None else None
        #     rule_int = int(rule) if rule is not None else None
        # except (ValueError, TypeError):
        #     result["status"] = ComparisonStatus.ERROR
        #     result["reason"] = "Cannot convert to integer"
        #     return result
        #
        # # 精确匹配 - Exact match
        # if gold_int == rule_int:
        #     result["status"] = ComparisonStatus.EXACT_MATCH
        #     result["reason"] = "Exact match"
        #     result["similarity"] = 1.0
        # else:
        #     # 容差匹配 - Tolerance match
        #     difference = abs(gold_int - rule_int)
        #     if difference <= tolerance:
        #         result["status"] = ComparisonStatus.PARTIAL_MATCH
        #         result["reason"] = f"Within tolerance (diff={difference})"
        #         # 计算相似度 - Calculate similarity
        #         if gold_int != 0:
        #             similarity = 1.0 - min(difference / abs(gold_int), 1.0)
        #             result["similarity"] = similarity
        #         else:
        #             result["similarity"] = 1.0
        #     else:
        #         result["status"] = ComparisonStatus.MISMATCH
        #         result["reason"] = f"Difference {difference} exceeds tolerance {tolerance}"
        #         if gold_int != 0:
        #             result["similarity"] = max(0.0, 1.0 - min(difference / abs(gold_int), 1.0))
        #
        # result["details"] = {
        #     "gold_value": gold_int,
        #     "rule_value": rule_int,
        #     "difference": difference,
        #     "tolerance": tolerance
        # }
        #
        # return result
        return {}

    @staticmethod
    def compare_floats(gold: float, rule: float, tolerance: float = 0.01) -> Dict[str, Any]:
        """
        浮点数对比
        Float comparison

        支持精确匹配、容差匹配
        Supports exact match, tolerance match

        伪代码 Pseudocode:
        1. 检查gold值是否为空
           Check if gold value is empty
        2. 尝试精确匹配（考虑浮点数精度）
           Try exact match (considering float precision)
        3. 如果设置容差，检查相对/绝对误差
           If tolerance set, check relative/absolute error
        4. 计算误差百分比
           Calculate error percentage
        5. 返回对比结果
           Return comparison result

        参数 Parameters:
            gold: gold标准值 - Gold standard value
            rule: 规则提取值 - Rule extracted value
            tolerance: 容差值 - Tolerance value

        返回 Returns:
            Dict[str, Any]: 对比结果 - Comparison result
        """
        # 伪代码实现 - Pseudocode implementation
        # result = {
        #     "status": ComparisonStatus.MISMATCH,
        #     "reason": "",
        #     "similarity": 0.0,
        #     "details": {}
        # }
        #
        # # 处理gold为空的情况 - Handle gold is None case
        # if gold is None:
        #     if rule is None:
        #         result["status"] = ComparisonStatus.EXACT_MATCH
        #         result["reason"] = "Both values are None"
        #     else:
        #         result["status"] = ComparisonStatus.MISMATCH
        #         result["reason"] = "Gold is None but rule has value"
        #     return result
        #
        # # 类型转换处理 - Type conversion handling
        # try:
        #     gold_float = float(gold) if gold is not None else None
        #     rule_float = float(rule) if rule is not None else None
        # except (ValueError, TypeError):
        #     result["status"] = ComparisonStatus.ERROR
        #     result["reason"] = "Cannot convert to float"
        #     return result
        #
        # # 精确匹配（考虑浮点精度） - Exact match (considering float precision)
        # if abs(gold_float - rule_float) < 1e-9:
        #     result["status"] = ComparisonStatus.EXACT_MATCH
        #     result["reason"] = "Exact match (within float precision)"
        #     result["similarity"] = 1.0
        # else:
        #     # 容差匹配 - Tolerance match
        #     absolute_error = abs(gold_float - rule_float)
        #     relative_error = absolute_error / abs(gold_float) if gold_float != 0 else float('inf')
        #
        #     if absolute_error <= tolerance:
        #         result["status"] = ComparisonStatus.PARTIAL_MATCH
        #         result["reason"] = f"Within absolute tolerance (error={absolute_error:.6f})"
        #         result["similarity"] = max(0.0, 1.0 - absolute_error)
        #     elif relative_error <= tolerance:
        #         result["status"] = ComparisonStatus.PARTIAL_MATCH
        #         result["reason"] = f"Within relative tolerance (error={relative_error:.2%})"
        #         result["similarity"] = max(0.0, 1.0 - relative_error)
        #     else:
        #         result["status"] = ComparisonStatus.MISMATCH
        #         result["reason"] = f"Error exceeds tolerance (abs={absolute_error:.6f}, rel={relative_error:.2%})"
        #         result["similarity"] = max(0.0, 1.0 - relative_error)
        #
        # result["details"] = {
        #     "gold_value": gold_float,
        #     "rule_value": rule_float,
        #     "absolute_error": absolute_error,
        #     "relative_error": relative_error,
        #     "tolerance": tolerance
        # }
        #
        # return result
        return {}

    @staticmethod
    def compare_lists(gold: list, rule: list, order_sensitive: bool = False) -> Dict[str, Any]:
        """
        列表对比
        List comparison

        支持精确匹配、部分匹配、顺序无关匹配
        Supports exact match, partial match, order-independent match

        伪代码 Pseudocode:
        1. 检查gold值是否为空
           Check if gold value is empty
        2. 检查长度是否相同
           Check if lengths are the same
        3. 如果顺序敏感，逐个元素对比
           If order sensitive, compare elements one by one
        4. 如果顺序不敏感，使用集合对比
           If order insensitive, use set comparison
        5. 计算重合度和覆盖率
           Calculate overlap and coverage
        6. 返回对比结果
           Return comparison result

        参数 Parameters:
            gold: gold标准值 - Gold standard value
            rule: 规则提取值 - Rule extracted value
            order_sensitive: 是否顺序敏感 - Whether order is sensitive

        返回 Returns:
            Dict[str, Any]: 对比结果 - Comparison result
        """
        # 伪代码实现 - Pseudocode implementation
        # result = {
        #     "status": ComparisonStatus.MISMATCH,
        #     "reason": "",
        #     "similarity": 0.0,
        #     "details": {}
        # }
        #
        # # 处理gold为空的情况 - Handle gold is None case
        # if gold is None:
        #     if rule is None or len(rule) == 0:
        #         result["status"] = ComparisonStatus.EXACT_MATCH
        #         result["reason"] = "Both lists are None/empty"
        #     else:
        #         result["status"] = ComparisonStatus.MISMATCH
        #         result["reason"] = "Gold is None/empty but rule has elements"
        #     return result
        #
        # # 检查长度 - Check lengths
        # gold_len = len(gold)
        # rule_len = len(rule)
        #
        # # 顺序敏感对比 - Order sensitive comparison
        # if order_sensitive:
        #     if gold == rule:
        #         result["status"] = ComparisonStatus.EXACT_MATCH
        #         result["reason"] = "Exact match (order sensitive)"
        #         result["similarity"] = 1.0
        #     else:
        #         # 逐个元素对比 - Compare elements one by one
        #         matches = sum(1 for g, r in zip(gold, rule) if g == r)
        #         similarity = matches / max(gold_len, rule_len)
        #         result["similarity"] = similarity
        #
        #         if similarity >= 0.9:
        #             result["status"] = ComparisonStatus.PARTIAL_MATCH
        #             result["reason"] = f"High similarity ({similarity:.2f})"
        #         else:
        #             result["status"] = ComparisonStatus.MISMATCH
        #             result["reason"] = f"Low similarity ({similarity:.2f})"
        # else:
        #     # 顺序不敏感对比 - Order insensitive comparison
        #     gold_set = set(gold) if all(isinstance(x, (str, int, float)) for x in gold) else gold
        #     rule_set = set(rule) if all(isinstance(x, (str, int, float)) for x in rule) else rule
        #
        #     # 如果元素可哈希，使用集合运算 - If elements are hashable, use set operations
        #     if isinstance(gold_set, set) and isinstance(rule_set, set):
        #         intersection = gold_set & rule_set
        #         union = gold_set | rule_set
        #         similarity = len(intersection) / len(union) if union else 0.0
        #     else:
        #         # 对于不可哈希元素，使用列表对比 - For non-hashable elements, use list comparison
        #         intersection_count = sum(1 for r in rule if r in gold)
        #         union_count = gold_len + rule_len - intersection_count
        #         similarity = intersection_count / union_count if union_count else 0.0
        #
        #     result["similarity"] = similarity
        #
        #     if similarity >= 0.95:
        #         result["status"] = ComparisonStatus.EXACT_MATCH
        #         result["reason"] = "Near perfect match (order insensitive)"
        #     elif similarity >= 0.7:
        #         result["status"] = ComparisonStatus.PARTIAL_MATCH
        #         result["reason"] = f"High overlap ({similarity:.2f})"
        #     else:
        #         result["status"] = ComparisonStatus.MISMATCH
        #         result["reason"] = f"Low overlap ({similarity:.2f})"
        #
        # result["details"] = {
        #     "gold_length": gold_len,
        #     "rule_length": rule_len,
        #     "length_diff": gold_len - rule_len,
        #     "order_sensitive": order_sensitive
        # }
        #
        # return result
        return {}

    @staticmethod
    def compare_dicts(gold: dict, rule: dict, partial_match: bool = False) -> Dict[str, Any]:
        """
        字典对比
        Dictionary comparison

        支持精确匹配、部分匹配
        Supports exact match, partial match

        伪代码 Pseudocode:
        1. 检查gold值是否为空
           Check if gold value is empty
        2. 检查keys是否完全匹配
           Check if keys match exactly
        3. 递归对比每个key的value
           Recursively compare value for each key
        4. 如果启用部分匹配，检查是否有共同keys
           If partial match enabled, check if there are common keys
        5. 计算key和value的匹配率
           Calculate key and value match rates
        6. 返回对比结果
           Return comparison result

        参数 Parameters:
            gold: gold标准值 - Gold standard value
            rule: 规则提取值 - Rule extracted value
            partial_match: 是否允许部分匹配 - Whether to allow partial match

        返回 Returns:
            Dict[str, Any]: 对比结果 - Comparison result
        """
        # 伪代码实现 - Pseudocode implementation
        # result = {
        #     "status": ComparisonStatus.MISMATCH,
        #     "reason": "",
        #     "similarity": 0.0,
        #     "details": {}
        # }
        #
        # # 处理gold为空的情况 - Handle gold is None case
        # if gold is None:
        #     if rule is None or len(rule) == 0:
        #         result["status"] = ComparisonStatus.EXACT_MATCH
        #         result["reason"] = "Both dicts are None/empty"
        #     else:
        #         result["status"] = ComparisonStatus.MISMATCH
        #         result["reason"] = "Gold is None/empty but rule has keys"
        #     return result
        #
        # gold_keys = set(gold.keys())
        # rule_keys = set(rule.keys())
        #
        # # 精确keys匹配 - Exact key match
        # if gold_keys == rule_keys:
        #     # 对比所有values - Compare all values
        #     value_matches = 0
        #     total_keys = len(gold_keys)
        #
        #     for key in gold_keys:
        #         if gold[key] == rule[key]:
        #             value_matches += 1
        #
        #     similarity = value_matches / total_keys if total_keys > 0 else 0.0
        #     result["similarity"] = similarity
        #
        #     if similarity == 1.0:
        #         result["status"] = ComparisonStatus.EXACT_MATCH
        #         result["reason"] = "Exact match"
        #     elif similarity >= 0.8:
        #         result["status"] = ComparisonStatus.PARTIAL_MATCH
        #         result["reason"] = f"High value similarity ({similarity:.2f})"
        #     else:
        #         result["status"] = ComparisonStatus.MISMATCH
        #         result["reason"] = f"Low value similarity ({similarity:.2f})"
        # else:
        #     # Keys不完全匹配 - Keys don't match exactly
        #     common_keys = gold_keys & rule_keys
        #     missing_keys = gold_keys - rule_keys
        #     extra_keys = rule_keys - gold_keys
        #
        #     # 如果不允许部分匹配 - If partial match not allowed
        #     if not partial_match:
        #         result["status"] = ComparisonStatus.MISMATCH
        #         result["reason"] = f"Keys don't match (missing={missing_keys}, extra={extra_keys})"
        #         # 计算相似度 - Calculate similarity
        #         if len(gold_keys) > 0:
        #             result["similarity"] = len(common_keys) / len(gold_keys)
        #     else:
        #         # 允许部分匹配 - Allow partial match
        #         # 对比共同keys的values - Compare values of common keys
        #         value_matches = 0
        #         for key in common_keys:
        #             if gold[key] == rule[key]:
        #                 value_matches += 1
        #
        #         if len(common_keys) > 0:
        #             value_similarity = value_matches / len(common_keys)
        #         else:
        #             value_similarity = 0.0
        #
        #         # 综合相似度 - Overall similarity
        #         key_similarity = len(common_keys) / len(gold_keys) if gold_keys else 0.0
        #         similarity = (key_similarity + value_similarity) / 2
        #         result["similarity"] = similarity
        #
        #         if similarity >= 0.7:
        #             result["status"] = ComparisonStatus.PARTIAL_MATCH
        #             result["reason"] = f"Partial match (similarity={similarity:.2f})"
        #         else:
        #             result["status"] = ComparisonStatus.MISMATCH
        #             result["reason"] = f"Low partial similarity ({similarity:.2f})"
        #
        # result["details"] = {
        #     "gold_keys": sorted(gold_keys),
        #     "rule_keys": sorted(rule_keys),
        #     "common_keys": sorted(common_keys),
        #     "missing_keys": sorted(missing_keys),
        #     "extra_keys": sorted(extra_keys),
        #     "partial_match": partial_match
        # }
        #
        # return result
        return {}

    @staticmethod
    def compare_booleans(gold: bool, rule: bool) -> Dict[str, Any]:
        """
        布尔对比
        Boolean comparison

        支持精确匹配
        Supports exact match

        伪代码 Pseudocode:
        1. 检查gold值是否为空
           Check if gold value is empty
        2. 转换为布尔类型
           Convert to boolean type
        3. 对比两个布尔值
           Compare two boolean values
        4. 返回对比结果
           Return comparison result

        参数 Parameters:
            gold: gold标准值 - Gold standard value
            rule: 规则提取值 - Rule extracted value

        返回 Returns:
            Dict[str, Any]: 对比结果 - Comparison result
        """
        # 伪代码实现 - Pseudocode implementation
        # result = {
        #     "status": ComparisonStatus.MISMATCH,
        #     "reason": "",
        #     "similarity": 0.0,
        #     "details": {}
        # }
        #
        # # 处理gold为空的情况 - Handle gold is None case
        # if gold is None:
        #     if rule is None:
        #         result["status"] = ComparisonStatus.EXACT_MATCH
        #         result["reason"] = "Both values are None"
        #     else:
        #         result["status"] = ComparisonStatus.MISMATCH
        #         result["reason"] = "Gold is None but rule has value"
        #     return result
        #
        # # 类型转换处理 - Type conversion handling
        # try:
        #     gold_bool = bool(gold)
        #     rule_bool = bool(rule)
        # except Exception:
        #     result["status"] = ComparisonStatus.ERROR
        #     result["reason"] = "Cannot convert to boolean"
        #     return result
        #
        # # 精确匹配 - Exact match
        # if gold_bool == rule_bool:
        #     result["status"] = ComparisonStatus.EXACT_MATCH
        #     result["reason"] = "Exact match"
        #     result["similarity"] = 1.0
        # else:
        #     result["status"] = ComparisonStatus.MISMATCH
        #     result["reason"] = "Boolean values don't match"
        #     result["similarity"] = 0.0
        #
        # result["details"] = {
        #     "gold_value": gold_bool,
        #     "rule_value": rule_bool
        # }
        #
        # return result
        return {}

    @staticmethod
    def calculate_similarity(gold: Any, rule: Any, field_type: str) -> float:
        """
        计算两个值的相似度
        Calculate similarity between two values

        伪代码 Pseudocode:
        1. 根据字段类型选择相似度计算方法
           Select similarity calculation method based on field type
        2. 返回0.0到1.0之间的相似度值
           Return similarity value between 0.0 and 1.0

        参数 Parameters:
            gold: gold标准值 - Gold standard value
            rule: 规则提取值 - Rule extracted value
            field_type: 字段类型 - Field type

        返回 Returns:
            float: 相似度值（0.0-1.0） - Similarity value (0.0-1.0)
        """
        # 伪代码实现 - Pseudocode implementation
        # comparison = FieldComparator.compare(gold, rule, field_type)
        # return comparison.get("similarity", 0.0)
        return 0.0