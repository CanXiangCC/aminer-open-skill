"""
规则提取实验框架 - Rule Extraction Experiment Framework

该框架提供通用的规则提取效果评估功能
This module provides universal rule extraction evaluation functionality

主要组件 Main Components:
- UniversalRuleEvaluator: 通用评估器 - Universal evaluator
- FieldComparator: 字段对比器 - Field comparator
- MetricsCalculator: 指标计算器 - Metrics calculator
- ReportGenerator: 报告生成器 - Report generator

使用方法 Usage:
    from rule_extraction_experiment.common import UniversalRuleEvaluator, FieldEvaluationConfig

    # 创建评估配置 - Create evaluation configuration
    config = FieldEvaluationConfig(
        field_name="sample_size",
        field_type="int",
        test_set="dev_10",
        gold_set="full_text_glm5_2",
        rule_module="src.rule_extraction.rules.sample_size",
        rule_class="SampleSizeRule",
        rule_params={"section_filter": True},
        metrics=["accuracy", "coverage"],
        data_paths={"gold_data_dir": "data/gold", ...}
    )

    # 运行评估 - Run evaluation
    evaluator = UniversalRuleEvaluator(config)
    result = evaluator.run_full_evaluation()
"""

__version__ = "0.1.0"
__author__ = "Zhipu Intern Team"
__description__ = "Universal framework for rule extraction evaluation"

# 导出主要组件 - Export main components
from .common.evaluator import UniversalRuleEvaluator, FieldEvaluationConfig, EvaluationResult
from .common.field_comparator import FieldComparator, ComparisonStatus
from .common.metrics import MetricsCalculator, EvaluationMetrics
from .common.report_generator import ReportGenerator

__all__ = [
    # 版本信息 - Version information
    "__version__",
    "__author__",
    "__description__",

    # 核心组件 - Core components
    "UniversalRuleEvaluator",
    "FieldEvaluationConfig",
    "EvaluationResult",

    # 对比组件 - Comparison components
    "FieldComparator",
    "ComparisonStatus",

    # 指标组件 - Metrics components
    "MetricsCalculator",
    "EvaluationMetrics",

    # 报告组件 - Report components
    "ReportGenerator",
]