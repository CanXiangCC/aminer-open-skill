"""
规则模块 - Rules Module

包含各种字段的规则提取实现
Contains rule extraction implementations for various fields

主要规则 Main Rules:
- paper_id: 论文ID提取 - Paper ID extraction
- sample_size: 样本大小提取 - Sample size extraction
- domain: 领域提取 - Domain extraction
- experiment_type: 实验类型提取 - Experiment type extraction
"""

__all__ = [
    "PaperIDRule",
    "SampleSizeRule",
    "DomainRule",
    "ExperimentTypeRule",
]