"""
评估指标计算器 - Evaluation Metrics Calculator

提供各类评估指标的计算功能
Provides calculation functions for various evaluation metrics

主要指标 Main Metrics:
- accuracy: 准确率 - Accuracy
- precision: 精确率 - Precision
- recall: 召回率 - Recall
- f1_score: F1分数 - F1 score
- coverage: 覆盖率 - Coverage
- classification_report: 分类报告 - Classification report
"""

from typing import Dict, Any, List, Set
from collections import Counter, defaultdict


class EvaluationMetrics:
    """评估指标类 - Evaluation Metrics Class"""

    def __init__(self):
        """初始化指标容器 - Initialize metrics container"""
        self.accuracy: float = 0.0
        self.precision: float = 0.0
        self.recall: float = 0.0
        self.f1_score: float = 0.0
        self.coverage: float = 0.0
        self.extraction_rate: float = 0.0

        # 统计信息 - Statistics
        self.total_papers: int = 0
        self.exact_matches: int = 0
        self.partial_matches: int = 0
        self.mismatches: int = 0
        self.missing: int = 0

        # 分类统计（适用于分类字段） - Classification statistics (for categorical fields)
        self.classification_stats: Dict[str, Dict[str, int]] = {}

    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典
        Convert to dictionary

        返回 Returns:
            Dict[str, Any]: 指标字典 - Metrics dictionary
        """
        return {
            "accuracy": self.accuracy,
            "precision": self.precision,
            "recall": self.recall,
            "f1_score": self.f1_score,
            "coverage": self.coverage,
            "extraction_rate": self.extraction_rate,
            "statistics": {
                "total_papers": self.total_papers,
                "exact_matches": self.exact_matches,
                "partial_matches": self.partial_matches,
                "mismatches": self.mismatches,
                "missing": self.missing
            },
            "classification_stats": self.classification_stats
        }


class MetricsCalculator:
    """
    指标计算器 - Metrics Calculator

    核心功能 Core Functions:
    1. 计算基础分类指标 - Calculate basic classification metrics
    2. 计算覆盖率 - Calculate coverage
    3. 计算提取成功率 - Calculate extraction success rate
    4. 生成分类报告 - Generate classification report
    """

    @staticmethod
    def calculate_basic_metrics(comparison_results: Dict[str, Any],
                                 include_partial: bool = False) -> Dict[str, float]:
        """
        计算基础指标
        Calculate basic metrics

        伪代码 Pseudocode:
        1. 统计各类匹配状态的数量
           Count numbers in each match status category
        2. 计算total数量
           Calculate total count
        3. 计算准确率（精确匹配 / 总数）
           Calculate accuracy (exact matches / total)
        4. 如果启用部分匹配，计算调整后的准确率
           If partial match enabled, calculate adjusted accuracy
        5. 返回指标字典
           Return metrics dictionary

        参数 Parameters:
            comparison_results: 对比结果字典 - Comparison results dictionary
            include_partial: 是否包含部分匹配 - Whether to include partial matches

        返回 Returns:
            Dict[str, float]: 基础指标 - Basic metrics
        """
        # 伪代码实现 - Pseudocode implementation
        # metrics = {}
        # total = len(comparison_results)
        #
        # if total == 0:
        #     return {"error": "No comparison results"}
        #
        # # 统计各类匹配 - Count match types
        # exact_matches = sum(1 for r in comparison_results.values()
        #                     if r.get("match_status") == "exact_match")
        # partial_matches = sum(1 for r in comparison_results.values()
        #                      if r.get("match_status") == "partial_match")
        # mismatches = sum(1 for r in comparison_results.values()
        #                  if r.get("match_status") == "mismatch")
        # missing = sum(1 for r in comparison_results.values()
        #              if r.get("match_status") == "missing")
        #
        # # 计算准确率 - Calculate accuracy
        # metrics["accuracy"] = exact_matches / total
        #
        # # 计算调整准确率（包含部分匹配） - Calculate adjusted accuracy (including partial matches)
        # if include_partial:
        #     adjusted_matches = exact_matches + (partial_matches * 0.5)  # 部分匹配算0.5分 - Partial match counts as 0.5
        #     metrics["adjusted_accuracy"] = adjusted_matches / total
        #
        # # 计算覆盖率 - Calculate coverage
        # metrics["coverage"] = 1.0 - (missing / total)
        #
        # # 计算错误率 - Calculate error rate
        # metrics["error_rate"] = mismatches / total
        #
        # # 计算缺失率 - Calculate missing rate
        # metrics["missing_rate"] = missing / total
        #
        # # 统计信息 - Statistics
        # metrics["statistics"] = {
        #     "total": total,
        #     "exact_matches": exact_matches,
        #     "partial_matches": partial_matches,
        #     "mismatches": mismatches,
        #     "missing": missing
        # }
        #
        # return metrics
        return {}

    @staticmethod
    def calculate_precision_recall_f1(comparison_results: Dict[str, Any],
                                       field_type: str) -> Dict[str, float]:
        """
        计算精确率、召回率、F1分数
        Calculate precision, recall, F1 score

        伪代码 Pseudocode:
        1. 根据字段类型确定TP、FP、FN的定义
           Determine definitions of TP, FP, FN based on field type
        2. 统计各类别的数量
           Count numbers in each category
        3. 计算precision = TP / (TP + FP)
           Calculate precision = TP / (TP + FP)
        4. 计算recall = TP / (TP + FN)
           Calculate recall = TP / (TP + FN)
        5. 计算F1 = 2 * (precision * recall) / (precision + recall)
           Calculate F1 = 2 * (precision * recall) / (precision + recall)
        6. 返回指标字典
           Return metrics dictionary

        参数 Parameters:
            comparison_results: 对比结果字典 - Comparison results dictionary
            field_type: 字段类型 - Field type

        返回 Returns:
            Dict[str, float]: 指标字典 - Metrics dictionary
        """
        # 伪代码实现 - Pseudocode implementation
        # metrics = {}
        # total = len(comparison_results)
        #
        # if total == 0:
        #     return {"error": "No comparison results"}
        #
        # # 统计各类匹配 - Count match types
        # exact_matches = sum(1 for r in comparison_results.values()
        #                     if r.get("match_status") == "exact_match")
        # partial_matches = sum(1 for r in comparison_results.values()
        #                      if r.get("match_status") == "partial_match")
        # mismatches = sum(1 for r in comparison_results.values()
        #                  if r.get("match_status") == "mismatch")
        # missing = sum(1 for r in comparison_results.values()
        #              if r.get("match_status") == "missing")
        #
        # # 根据字段类型定义TP、FP、FN - Define TP, FP, FN based on field type
        # # 对于大多数字段： - For most fields:
        # # TP (True Positive): 精确匹配 - Exact match
        # # FP (False Positive): 不匹配 - Mismatch
        # # FN (False Negative): 缺失 - Missing
        # # 部分匹配可以视为半成功 - Partial matches can be treated as half success
        #
        # tp = exact_matches + (partial_matches * 0.5)
        # fp = mismatches
        # fn = missing
        #
        # # 计算精确率 - Calculate precision
        # if tp + fp > 0:
        #     metrics["precision"] = tp / (tp + fp)
        # else:
        #     metrics["precision"] = 0.0
        #
        # # 计算召回率 - Calculate recall
        # if tp + fn > 0:
        #     metrics["recall"] = tp / (tp + fn)
        # else:
        #     metrics["recall"] = 0.0
        #
        # # 计算F1分数 - Calculate F1 score
        # if metrics["precision"] + metrics["recall"] > 0:
        #     metrics["f1_score"] = 2 * (metrics["precision"] * metrics["recall"]) / (metrics["precision"] + metrics["recall"])
        # else:
        #     metrics["f1_score"] = 0.0
        #
        # return metrics
        return {}

    @staticmethod
    def generate_classification_report(comparison_results: Dict[str, Any],
                                       gold_values: List[Any],
                                       rule_values: List[Any]) -> Dict[str, Any]:
        """
        生成分类报告
        Generate classification report

        适用于分类字段（如domain、experiment_type）
        Applicable for categorical fields (like domain, experiment_type)

        伪代码 Pseudocode:
        1. 统计所有出现的类别
           Count all appearing categories
        2. 构建混淆矩阵
           Build confusion matrix
        3. 为每个类别计算precision、recall、f1
           Calculate precision, recall, f1 for each category
        4. 计算宏观平均和微观平均
           Calculate macro average and micro average
        5. 返回详细的分类报告
           Return detailed classification report

        参数 Parameters:
            comparison_results: 对比结果字典 - Comparison results dictionary
            gold_values: gold值列表 - Gold value list
            rule_values: 规则提取值列表 - Rule extracted value list

        返回 Returns:
            Dict[str, Any]: 分类报告 - Classification report
        """
        # 伪代码实现 - Pseudocode implementation
        # report = {
        #     "per_class": {},
        #     "macro_avg": {},
        #     "micro_avg": {},
        #     "weighted_avg": {}
        # }
        #
        # # 构建类别统计 - Build category statistics
        # gold_classes = [str(g) for g in gold_values if g is not None]
        # rule_classes = [str(r) for r in rule_values if r is not None]
        #
        # # 获取所有类别 - Get all categories
        # all_classes = sorted(set(gold_classes + rule_classes))
        #
        # # 构建混淆矩阵 - Build confusion matrix
        # confusion_matrix = defaultdict(lambda: defaultdict(int))
        # for gold_class, rule_class in zip(gold_classes, rule_classes):
        #     confusion_matrix[gold_class][rule_class] += 1
        #
        # # 为每个类别计算指标 - Calculate metrics for each class
        # for true_class in all_classes:
        #     true_positives = confusion_matrix[true_class][true_class]
        #     false_positives = sum(confusion_matrix[other_class][true_class] for other_class in all_classes if other_class != true_class)
        #     false_negatives = sum(confusion_matrix[true_class][other_class] for other_class in all_classes if other_class != true_class)
        #
        #     # 计算该类别的指标 - Calculate metrics for this class
        #     precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0
        #     recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0.0
        #     f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        #     support = gold_classes.count(true_class)
        #
        #     report["per_class"][true_class] = {
        #         "precision": precision,
        #         "recall": recall,
        #         "f1_score": f1,
        #         "support": support
        #     }
        #
        # # 计算宏平均 - Calculate macro average
        # precisions = [report["per_class"][c]["precision"] for c in all_classes]
        # recalls = [report["per_class"][c]["recall"] for c in all_classes]
        # f1s = [report["per_class"][c]["f1_score"] for c in all_classes]
        #
        # report["macro_avg"] = {
        #     "precision": sum(precisions) / len(precisions) if precisions else 0.0,
        #     "recall": sum(recalls) / len(recalls) if recalls else 0.0,
        #     "f1_score": sum(f1s) / len(f1s) if f1s else 0.0
        # }
        #
        # # 计算微平均 - Calculate micro average
        # total_tp = sum(confusion_matrix[c][c] for c in all_classes)
        # total_fp = sum(confusion_matrix[other_class][true_class] for true_class in all_classes for other_class in all_classes if other_class != true_class)
        # total_fn = sum(confusion_matrix[true_class][other_class] for true_class in all_classes for other_class in all_classes if other_class != true_class)
        #
        # micro_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
        # micro_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
        # micro_f1 = 2 * (micro_precision * micro_recall) / (micro_precision + micro_recall) if (micro_precision + micro_recall) > 0 else 0.0
        #
        # report["micro_avg"] = {
        #     "precision": micro_precision,
        #     "recall": micro_recall,
        #     "f1_score": micro_f1
        # }
        #
        # # 计算加权平均 - Calculate weighted average
        # total_support = sum(report["per_class"][c]["support"] for c in all_classes)
        # weighted_precision = sum(report["per_class"][c]["precision"] * report["per_class"][c]["support"] for c in all_classes) / total_support if total_support > 0 else 0.0
        # weighted_recall = sum(report["per_class"][c]["recall"] * report["per_class"][c]["support"] for c in all_classes) / total_support if total_support > 0 else 0.0
        # weighted_f1 = sum(report["per_class"][c]["f1_score"] * report["per_class"][c]["support"] for c in all_classes) / total_support if total_support > 0 else 0.0
        #
        # report["weighted_avg"] = {
        #     "precision": weighted_precision,
        #     "recall": weighted_recall,
        #     "f1_score": weighted_f1
        # }
        #
        # # 添加混淆矩阵 - Add confusion matrix
        # report["confusion_matrix"] = {
        #     true_class: dict(confusion_matrix[true_class])
        #     for true_class in all_classes
        # }
        #
        # return report
        return {}

    @staticmethod
    def calculate_similarity_distribution(comparison_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        计算相似度分布
        Calculate similarity distribution

        伪代码 Pseudocode:
        1. 提取所有对比结果的相似度值
           Extract similarity values from all comparison results
        2. 统计相似度区间的分布
           Count distribution of similarity ranges
        3. 计算平均相似度、中位数、标准差
           Calculate mean, median, standard deviation of similarity
        4. 返回分布统计
           Return distribution statistics

        参数 Parameters:
            comparison_results: 对比结果字典 - Comparison results dictionary

        返回 Returns:
            Dict[str, Any]: 相似度分布 - Similarity distribution
        """
        # 伪代码实现 - Pseudocode implementation
        # import statistics
        #
        # # 提取相似度值 - Extract similarity values
        # similarities = [r.get("similarity", 0.0) for r in comparison_results.values()]
        #
        # if not similarities:
        #     return {"error": "No similarity data"}
        #
        # # 统计区间分布 - Count range distribution
        # ranges = {
        #     "0.0-0.2": 0,
        #     "0.2-0.4": 0,
        #     "0.4-0.6": 0,
        #     "0.6-0.8": 0,
        #     "0.8-1.0": 0
        # }
        #
        # for sim in similarities:
        #     if sim < 0.2:
        #         ranges["0.0-0.2"] += 1
        #     elif sim < 0.4:
        #         ranges["0.2-0.4"] += 1
        #     elif sim < 0.6:
        #         ranges["0.4-0.6"] += 1
        #     elif sim < 0.8:
        #         ranges["0.6-0.8"] += 1
        #     else:
        #         ranges["0.8-1.0"] += 1
        #
        # # 计算统计量 - Calculate statistics
        # distribution = {
        #     "mean": statistics.mean(similarities),
        #     "median": statistics.median(similarities),
        #     "std": statistics.stdev(similarities) if len(similarities) > 1 else 0.0,
        #     "min": min(similarities),
        #     "max": max(similarities),
        #     "ranges": ranges
        # }
        #
        # return distribution
        return {}

    @staticmethod
    def calculate_extraction_metrics(extraction_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        计算提取相关指标
        Calculate extraction-related metrics

        伪代码 Pseudocode:
        1. 统计成功提取和失败提取的数量
           Count successful and failed extractions
        2. 计算提取成功率
           Calculate extraction success rate
        3. 统计各类错误类型
           Count error types
        4. 返回提取指标
           Return extraction metrics

        参数 Parameters:
            extraction_results: 提取结果字典 - Extraction results dictionary

        返回 Returns:
            Dict[str, Any]: 提取指标 - Extraction metrics
        """
        # 伪代码实现 - Pseudocode implementation
        # metrics = {}
        # total = len(extraction_results)
        #
        # if total == 0:
        #     return {"error": "No extraction results"}
        #
        # # 统计提取状态 - Count extraction status
        # successful = sum(1 for r in extraction_results.values()
        #                  if r.get("status") == "success")
        # failed = sum(1 for r in extraction_results.values()
        #               if r.get("status") == "failed")
        #
        # # 计算提取成功率 - Calculate extraction success rate
        # metrics["extraction_rate"] = successful / total
        # metrics["extraction_success"] = successful
        # metrics["extraction_failed"] = failed
        # metrics["extraction_total"] = total
        #
        # # 统计错误类型 - Count error types
        # error_types = defaultdict(int)
        # for r in extraction_results.values():
        #     if r.get("status") == "failed" and r.get("error"):
        #         error_types[r["error"]] += 1
        #
        # metrics["error_types"] = dict(error_types)
        #
        # return metrics
        return {}

    @staticmethod
    def calculate_time_comparison(baseline_time: float,
                                   rule_time: float) -> Dict[str, Any]:
        """
        计算时间对比
        Calculate time comparison

        伪代码 Pseudocode:
        1. 计算时间节省比例
           Calculate time saving percentage
        2. 计算加速比
           Calculate speedup ratio
        3. 返回对比结果
           Return comparison result

        参数 Parameters:
            baseline_time: 基线时间 - Baseline time
            rule_time: 规则提取时间 - Rule extraction time

        返回 Returns:
            Dict[str, Any]: 时间对比 - Time comparison
        """
        # 伪代码实现 - Pseudocode implementation
        # if baseline_time == 0:
        #     return {"error": "Baseline time is zero"}
        #
        # comparison = {
        #     "baseline_time": baseline_time,
        #     "rule_time": rule_time,
        #     "time_saved": baseline_time - rule_time,
        #     "time_saved_percentage": ((baseline_time - rule_time) / baseline_time) * 100,
        #     "speedup_ratio": baseline_time / rule_time if rule_time > 0 else float('inf')
        # }
        #
        # return comparison
        return {}

    @staticmethod
    def calculate_cost_comparison(baseline_cost: float,
                                   rule_cost: float) -> Dict[str, Any]:
        """
        计算成本对比
        Calculate cost comparison

        伪代码 Pseudocode:
        1. 计算成本节省比例
           Calculate cost saving percentage
        2. 计算成本降低倍数
           Calculate cost reduction factor
        3. 返回对比结果
           Return comparison result

        参数 Parameters:
            baseline_cost: 基线成本 - Baseline cost
            rule_cost: 规则提取成本 - Rule extraction cost

        返回 Returns:
            Dict[str, Any]: 成本对比 - Cost comparison
        """
        # 伪代码实现 - Pseudocode implementation
        # if baseline_cost == 0:
        #     return {"error": "Baseline cost is zero"}
        #
        # comparison = {
        #     "baseline_cost": baseline_cost,
        #     "rule_cost": rule_cost,
        #     "cost_saved": baseline_cost - rule_cost,
        #     "cost_saved_percentage": ((baseline_cost - rule_cost) / baseline_cost) * 100,
        #     "cost_reduction_factor": baseline_cost / rule_cost if rule_cost > 0 else float('inf')
        # }
        #
        # return comparison
        return {}

    @staticmethod
    def calculate_all_metrics(comparison_results: Dict[str, Any],
                               extraction_results: Dict[str, Any],
                               config_metrics: List[str],
                               field_type: str = "str") -> Dict[str, Any]:
        """
        计算所有请求的指标
        Calculate all requested metrics

        伪代码 Pseudocode:
        1. 根据配置的指标列表调用相应的计算方法
           Call corresponding calculation methods based on configured metrics list
        2. 收集所有计算结果
           Collect all calculation results
        3. 返回完整的指标字典
           Return complete metrics dictionary

        参数 Parameters:
            comparison_results: 对比结果字典 - Comparison results dictionary
            extraction_results: 提取结果字典 - Extraction results dictionary
            config_metrics: 配置的指标列表 - Configured metrics list
            field_type: 字段类型 - Field type

        返回 Returns:
            Dict[str, Any]: 完整的指标字典 - Complete metrics dictionary
        """
        # 伪代码实现 - Pseudocode implementation
        # metrics = {}
        #
        # # 基础指标 - Basic metrics
        # if any(m in config_metrics for m in ["accuracy", "coverage", "error_rate"]):
        #     basic_metrics = MetricsCalculator.calculate_basic_metrics(comparison_results)
        #     if "accuracy" in config_metrics:
        #         metrics["accuracy"] = basic_metrics.get("accuracy", 0.0)
        #     if "coverage" in config_metrics:
        #         metrics["coverage"] = basic_metrics.get("coverage", 0.0)
        #     if "error_rate" in config_metrics:
        #         metrics["error_rate"] = basic_metrics.get("error_rate", 0.0)
        #
        # # 分类指标 - Classification metrics
        # if any(m in config_metrics for m in ["precision", "recall", "f1_score"]):
        #     prf_metrics = MetricsCalculator.calculate_precision_recall_f1(
        #         comparison_results, field_type
        #     )
        #     if "precision" in config_metrics:
        #         metrics["precision"] = prf_metrics.get("precision", 0.0)
        #     if "recall" in config_metrics:
        #         metrics["recall"] = prf_metrics.get("recall", 0.0)
        #     if "f1_score" in config_metrics:
        #         metrics["f1_score"] = prf_metrics.get("f1_score", 0.0)
        #
        # # 提取指标 - Extraction metrics
        # if any(m in config_metrics for m in ["extraction_rate", "extraction_success"]):
        #     extraction_metrics = MetricsCalculator.calculate_extraction_metrics(extraction_results)
        #     if "extraction_rate" in config_metrics:
        #         metrics["extraction_rate"] = extraction_metrics.get("extraction_rate", 0.0)
        #     if "extraction_success" in config_metrics:
        #         metrics["extraction_success"] = extraction_metrics.get("extraction_success", 0)
        #
        # # 统计信息 - Statistics
        # if "statistics" in config_metrics or True:  # 总是包含统计信息 - Always include statistics
        #     basic_metrics = MetricsCalculator.calculate_basic_metrics(comparison_results)
        #     metrics["statistics"] = basic_metrics.get("statistics", {})
        #
        # return metrics
        return {}