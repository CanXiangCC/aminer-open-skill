"""
通用规则提取评估框架 - Universal Rule Extraction Evaluation Framework

该模块提供通用的规则提取效果评估功能
This module provides universal rule extraction evaluation functionality

主要组件 Main Components:
- UniversalRuleEvaluator: 通用评估器 - Universal evaluator
- FieldEvaluationConfig: 字段评估配置 - Field evaluation configuration
- EvaluationResult: 评估结果 - Evaluation result
"""

from .evaluator import UniversalRuleEvaluator, FieldEvaluationConfig, EvaluationResult
from .field_comparator import FieldComparator, ComparisonStatus
from .metrics import MetricsCalculator, EvaluationMetrics
from .report_generator import ReportGenerator

__version__ = "0.1.0"
__all__ = [
    "UniversalRuleEvaluator",
    "FieldEvaluationConfig",
    "EvaluationResult",
    "FieldComparator",
    "ComparisonStatus",
    "MetricsCalculator",
    "EvaluationMetrics",
    "ReportGenerator",
]