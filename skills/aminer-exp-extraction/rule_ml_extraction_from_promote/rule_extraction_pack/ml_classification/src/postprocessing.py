"""
后处理策略 - Post-processing Strategies

提供基于规则的后处理策略来辅助机器学习分类
Provides rule-based post-processing strategies to assist ML classification

策略说明 Strategy Description:
- strategy_1: 基于置信度+关键词的智能规则
  - 如果预测为comparison且置信度低(<0.6)
  - 并且文本包含'benchmark'关键词
  - 则改为benchmark
  - 效果: 整体准确率提升0.88%, benchmark准确率提升4.17%
"""

from typing import Optional
import numpy as np


def apply_strategy_1(
    text: str,
    pred_label: str,
    pred_proba: np.ndarray,
    classes: np.ndarray,
    confidence_threshold: float = 0.6
) -> str:
    """
    后处理策略1: 基于置信度+关键词的智能修正

    适用于 experiment_type 分类中的 benchmark vs comparison 混淆问题

    伪代码 Pseudocode:
    1. 检查预测是否为comparison
       Check if prediction is comparison
    2. 检查comparison的置信度是否低于阈值
       Check if comparison confidence is below threshold
    3. 检查文本是否包含'benchmark'关键词
       Check if text contains 'benchmark' keyword
    4. 如果以上条件都满足，将预测改为benchmark
       If all conditions met, change prediction to benchmark
    5. 否则保持原预测
       Otherwise keep original prediction

    参数 Parameters:
        text: 原始文本 - Original text
        pred_label: 预测标签 - Predicted label
        pred_proba: 预测概率分布 - Prediction probability distribution
        classes: 所有类别数组 - All classes array
        confidence_threshold: 置信度阈值 - Confidence threshold (默认0.6)

    返回 Returns:
        str: 后处理后的标签 - Post-processed label

    示例 Example:
        >>> text = "HQ-RAIN Benchmark and RE-RAIN Dataset Construction..."
        >>> pred_label = "comparison"
        >>> pred_proba = np.array([0.1, 0.18, 0.16, ...])  # comparison置信度0.18
        >>> classes = np.array(['ablation', 'benchmark', 'comparison', ...])
        >>> result = apply_strategy_1(text, pred_label, pred_proba, classes)
        >>> result  # 'benchmark'
    """
    # 伪代码实现 - Pseudocode implementation
    text_lower = text.lower()

    # 只针对comparison预测
    if pred_label != 'comparison':
        return pred_label

    # 获取comparison的索引和置信度
    comparison_idx = np.where(classes == 'comparison')[0]

    if len(comparison_idx) == 0:
        return pred_label

    comparison_confidence = pred_proba[comparison_idx[0]]

    # 检查是否包含benchmark关键词
    has_benchmark_keyword = 'benchmark' in text_lower

    # 规则: comparison置信度低且有benchmark关键词 → 改为benchmark
    if comparison_confidence < confidence_threshold and has_benchmark_keyword:
        return 'benchmark'

    return pred_label


def apply_strategy_1_batch(
    texts: list,
    pred_labels: list,
    pred_probas: np.ndarray,
    classes: np.ndarray,
    confidence_threshold: float = 0.6
) -> list:
    """
    批量应用策略1

    伪代码 Pseudocode:
    1. 遍历所有样本
       Iterate through all samples
    2. 对每个样本应用策略1
       Apply strategy 1 to each sample
    3. 返回处理后的标签列表
       Return processed label list

    参数 Parameters:
        texts: 文本列表 - Text list
        pred_labels: 预测标签列表 - Predicted label list
        pred_probas: 预测概率矩阵 - Prediction probability matrix
        classes: 所有类别数组 - All classes array
        confidence_threshold: 置信度阈值 - Confidence threshold

    返回 Returns:
        list: 后处理后的标签列表 - Post-processed label list
    """
    # 伪代码实现 - Pseudocode implementation
    results = []
    for i, (text, pred_label) in enumerate(zip(texts, pred_labels)):
        result = apply_strategy_1(
            text, pred_label, pred_probas[i], classes, confidence_threshold
        )
        results.append(result)
    return results


# 策略注册表 - Strategy Registry
STRATEGIES = {
    "strategy_1": {
        "name": "基于置信度+关键词的智能修正",
        "description": "适用于 experiment_type: comparison→benchmark (当置信度低且有benchmark关键词)",
        "function": apply_strategy_1,
        "batch_function": apply_strategy_1_batch,
        "params": {
            "confidence_threshold": 0.6,
            "target_field": "experiment_type",
        },
        "performance": {
            "accuracy_improvement": "+0.88%",
            "benchmark_accuracy": "+4.17%",
            "comparison_accuracy": "-1.00%",
            "modified_samples": 9,  # 340个测试样本中
            "correct_corrections": 4,
            "wrong_corrections": 5,
        },
    },
}


def get_strategy(strategy_name: str) -> Optional[dict]:
    """
    获取指定策略

    伪代码 Pseudocode:
    1. 查找策略
       Look up strategy
    2. 如果存在，返回策略信息
       If exists, return strategy info
    3. 否则返回None
       Otherwise return None

    参数 Parameters:
        strategy_name: 策略名称 - Strategy name

    返回 Returns:
        Optional[dict]: 策略信息或None - Strategy info or None
    """
    # 伪代码实现 - Pseudocode implementation
    return STRATEGIES.get(strategy_name)


def list_strategies() -> list:
    """
    列出所有可用策略

    伪代码 Pseudocode:
    1. 返回策略名称列表
       Return strategy name list

    返回 Returns:
        list: 策略名称列表 - Strategy name list
    """
    # 伪代码实现 - Pseudocode implementation
    return list(STRATEGIES.keys())


def apply_postprocessing(
    texts: list,
    pred_labels: list,
    pred_probas: np.ndarray,
    classes: np.ndarray,
    strategy_name: str = "strategy_1",
    **kwargs
) -> list:
    """
    应用指定的后处理策略

    伪代码 Pseudocode:
    1. 获取策略
       Get strategy
    2. 如果策略不存在，返回原预测
       If strategy not found, return original predictions
    3. 使用批量处理函数
       Use batch processing function
    4. 返回处理后的标签
       Return processed labels

    参数 Parameters:
        texts: 文本列表 - Text list
        pred_labels: 预测标签列表 - Predicted label list
        pred_probas: 预测概率矩阵 - Prediction probability matrix
        classes: 所有类别数组 - All classes array
        strategy_name: 策略名称 - Strategy name
        **kwargs: 策略参数 - Strategy parameters

    返回 Returns:
        list: 后处理后的标签列表 - Post-processed label list
    """
    # 伪代码实现 - Pseudocode implementation
    strategy = get_strategy(strategy_name)

    if strategy is None:
        print(f"警告: 策略 '{strategy_name}' 不存在，返回原预测")
        return pred_labels

    batch_func = strategy.get("batch_function")
    if batch_func:
        return batch_func(texts, pred_labels, pred_probas, classes, **kwargs)

    return pred_labels