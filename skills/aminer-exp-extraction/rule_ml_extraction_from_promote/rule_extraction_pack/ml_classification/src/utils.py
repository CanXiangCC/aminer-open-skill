"""
工具函数模块 - Utility Functions

辅助函数集合
Auxiliary functions

主要功能 Main Functions:
- 加载JSON数据
- 数据格式转换
- 评估指标计算
- 文本处理工具
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, List, Tuple


def load_json_data(directory: Path) -> List[Dict[str, Any]]:
    """
    从指定目录加载所有JSON数据
    Load all JSON data from specified directory

    伪代码 Pseudocode:
    1. 初始化结果列表
       Initialize result list
    2. 遍历目录中的JSON文件
       Iterate through JSON files in directory
    3. 读取每个JSON文件内容
       Read each JSON file content
    4. 解析JSON数据
       Parse JSON data
    5. 添加到结果列表
       Add to result list
    6. 返回数据列表
       Return data list

    参数 Parameters:
        directory: JSON文件目录 - JSON file directory

    返回 Returns:
        List[Dict[str, Any]]: 数据列表 - Data list
    """
    # 伪代码实现 - Pseudocode implementation
    data_list = []

    for json_file in directory.glob("*.json"):
        try:
            with open(json_file, 'r', encoding='utf-8', errors='ignore') as f:
                data = json.load(f)
                data_list.append(data)
        except json.JSONDecodeError:
            print(f"Error parsing {json_file.name}")
        except Exception as e:
            print(f"Error loading {json_file.name}: {e}")

    return data_list


def load_paper_md(paper_id: str, corpus_dir: Path) -> str:
    """
    根据paper_id加载论文md文件
    Load paper md file by paper_id

    伪代码 Pseudocode:
    1. 构建文件路径
       Build file path
    2. 检查文件是否存在
       Check if file exists
    3. 读取文件内容
       Read file content
    4. 返回内容
       Return content

    参数 Parameters:
        paper_id: 论文ID - Paper ID
        corpus_dir: 论文集目录 - Corpus directory

    返回 Returns:
        str: 论文markdown文本 - Paper markdown text
    """
    # 伪代码实现 - Pseudocode implementation
    file_path = corpus_dir / f"{paper_id}.md"

    if not file_path.exists():
        return ""

    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

    return ""


def load_extracted_field(paper_id: str, field_name: str, data_dir: Path) -> List[str]:
    """
    从JSON数据中提取特定字段的值
    Extract values of specific field from JSON data

    伪代码 Pseudocode:
    1. 遍历目录中的所有JSON文件
       Iterate through all JSON files in directory
    2. 对于每个JSON文件，如果包含paper_id
       For each JSON file, if contains paper_id:
        3. 提取指定字段的值
           Extract value of specified field
        4. 添加到结果列表
           Add to result list
    5. 返回值列表
       Return value list

    参数 Parameters:
        paper_id: 论文ID - Paper ID
        field_name: 字段名 - Field name
        data_dir: JSON文件目录 - JSON file directory

    返回 Returns:
        List[str]: 值列表 - Value list
    """
    # 伪代码实现 - Pseudocode implementation
    field_values = []

    for json_file in data_dir.glob("*.json"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 如果是数据集字段且对应paper_id匹配
            if field_name == "dataset_type":
                # 需要遍历该论文的所有实验
                if "datasets" in data:
                    for dataset in data["datasets"]:
                        field_values.append(dataset.get(field_name, "other"))
            elif "paper_id" in data and data["paper_id"] == paper_id:
                value = data.get(field_name)
                if value and value is not None:
                    field_values.append(str(value))

        except json.JSONDecodeError:
            pass

    return field_values


def create_text_label_pairs(papers: List[Dict[str, Any]], field_name: str) -> Tuple[List[str], List[str]]:
    """
    为指定字段创建文本-标签对
    Create text-label pairs for specified field

    伪代码 Pseudocode:
    1. 初始化文本列表和标签列表
       Initialize text and label lists
    2. 遍历每篇论文
       Iterate through each paper
    3. 提取字段的值
       Extract field value
    4. 如果有多个值，选择最合适的
           If multiple values, choose most appropriate
    5. 添加到文本和标签列表
       Add to text and label lists
    6. 返回文本-标签对
       Return text-label pairs

    参数 Parameters:
        papers: 论文数据列表 - Paper data list
        field_name: 字段名 - Field name

    返回 Returns:
        Tuple[List[str], List[str]]: 文本列表和标签列表 - Text list and label list
    """
    # 伪代码实现 - Pseudocode implementation
    texts = []
    labels = []

    for paper in papers:
        # 如果是数据集字段
        if field_name == "dataset_type":
            datasets = paper.get("datasets", [])
            for dataset in datasets:
                # 组合数据集文本
                text = f"{dataset.get('name', '')} {dataset.get('description', '')}"
                label = dataset.get(field_name, "other")
                texts.append(text)
                labels.append(label)
        else:
            # 其他字段通常每个论文只有一个值
            value = paper.get(field_name)
            if value and value is not None:
                # 从论文中提取文本
                # 简化版：使用标题和摘要
                title = paper.get("title", "")
                abstract = paper.get("abstract", "")
                text = f"{title} {abstract}"
                texts.append(text)
                labels.append(str(value))

    return texts, labels


def evaluate_model(y_true: List[str], y_pred: List[str], class_names: List[str]) -> Dict[str, Any]:
    """
    评估模型性能
    Evaluate model performance

    伪代码 Pseudocode:
    1. 导入真实的标签
       Input true labels
    2. 导入预测的标签
       Input predicted labels
    3. 计算准确率
       Calculate accuracy
    4. 计算分类报告
       Calculate classification report
    5. 返回评估结果
       Return evaluation result

    参数 Parameters:
        y_true: 真实标签列表 - True labels list
        y_pred: 预测标签列表 - Predicted labels list
        class_names: 类别名称列表 - Class names list

    返回 Returns:
        Dict[str, Any]: 评估结果 - Evaluation result
    """
    # 伪代码实现 - Pseudocode implementation
    # 计算准确率
    accuracy = sum(1 for yt, yp in zip(y_true, y_pred) if yt == yp) / len(y_true)

    # 生成分类报告
    from sklearn.metrics import classification_report

    # 转换为数值标签（确保与模型输出一致）
    y_true_indices = [class_names.index(yt) if yt in class_names else -1 for yt in y_true]
    y_pred_indices = [class_names.index(yp) if yp in class_names else -1 for yp in y_pred]

    # 计算指标
    report = classification_report(
        y_true_indices,
        y_pred_indices,
        target_names=class_names,
        output_dict=True
    )

    return {
        "accuracy": report["accuracy"],
        "classification_report": report,
        "n_samples": len(y_true)
    }


def print_feature_importance(feature_importance: List[Tuple[str, float]], class_name: str, n_top: int = 10):
    """
    打印特征重要性
    Print feature importance

    伪代码 Pseudocode:
    1. 打印类别名称
       Print class name
    2. 打印特征重要性
       Print feature importance
    3. 返回无
       Return None

    参数 Parameters:
        feature_importance: 特征重要性列表 - Feature importance list
        class_name: 类别名称 - Class name
        n_top: 显示前几个 - Show top n features
    """
    # 伪代码实现 - Pseudocode implementation
    print(f"\n{class_name}最重要的{n_top}个特征:")
    print("-" * 50)
    for feature_name, score in feature_importance[:n_top]:
        print(f"{feature_name}: {score:.4f}")
    print()