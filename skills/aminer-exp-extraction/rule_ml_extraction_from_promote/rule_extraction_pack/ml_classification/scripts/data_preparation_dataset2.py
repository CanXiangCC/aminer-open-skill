"""
数据预处理脚本 - 数据集2 (纯JSON特征)

所有分类任务的特征都从JSON文件中提取，无需MD文件
All classification features are extracted from JSON files, no MD files needed

主要功能 Main Functions:
- 从JSON标注数据中提取文本和标签
- Domain: 使用research_problem, research_goal, experiment_subject, method, conclusion, evidence
- Experiment_type: 使用experiment_name, evidence, method, key_results
- Dataset_type: 使用数据集name和description
- 数据集划分（训练集/测试集）
"""

import json
import sys
from pathlib import Path
from typing import List, Tuple
from collections import Counter

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
ML_CLASSIFICATION = PROJECT_ROOT / "ml_classification"
sys.path.insert(0, str(ML_CLASSIFICATION / "src"))


class DataPreparatorDataset2:
    """数据集2预处理器 - Dataset2 Data Preparator (JSON-only)"""

    def __init__(self, outputs_dir: Path, processed_dir: Path):
        """
        初始化数据预处理器
        Initialize data preparator

        参数 Parameters:
            outputs_dir: 标注JSON文件目录 - Annotated JSON files directory
            processed_dir: 处理后数据保存目录 - Processed data save directory
        """
        self.outputs_dir = outputs_dir
        self.processed_dir = processed_dir
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def prepare_domain_text(self, item: dict) -> str:
        """
        从JSON字段拼接domain分类文本特征
        Concatenate domain classification features from JSON fields

        参数 Parameters:
            item: JSON数据项 - JSON data item

        返回 Returns:
            str: 拼接后的文本 - Concatenated text
        """
        parts = []

        # 研究问题 (高权重)
        research_problem = item.get("research_problem", "")
        if research_problem:
            parts.append(research_problem)

        # 研究目标 (高权重)
        research_goal = item.get("research_goal", "")
        if research_goal:
            parts.append(research_goal)

        # 实验对象 (中权重)
        experiment_subject = item.get("experiment_subject", [])
        if isinstance(experiment_subject, list):
            parts.extend(str(s) for s in experiment_subject[:2])
        elif experiment_subject:
            parts.append(str(experiment_subject))

        # 研究方法 (中权重)
        method = item.get("method", "")
        if method:
            parts.append(method)

        # 结论 (中权重)
        conclusion = item.get("conclusion", "")
        if conclusion:
            parts.append(conclusion)

        # 证据 (低权重，最多2条)
        evidence = item.get("evidence", [])
        if isinstance(evidence, list):
            parts.extend(str(e) for e in evidence[:2])
        elif evidence:
            parts.append(str(evidence))

        return " ".join(parts)

    def prepare_domain_data(self) -> Tuple[List[str], List[str]]:
        """
        准备domain分类数据（从JSON提取）
        Prepare domain classification data (from JSON)

        返回 Returns:
            Tuple[List[str], List[str]]: 文本列表和标签列表 - Text list and label list
        """
        texts = []
        labels = []

        for json_file in self.outputs_dir.glob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8', errors='ignore') as f:
                    data = json.load(f)

                # 处理数组格式或单个对象格式
                items = data if isinstance(data, list) else [data]

                for item in items:
                    # 使用JSON字段拼接
                    text = self.prepare_domain_text(item)
                    domain = item.get("domain")

                    if text.strip() and domain:
                        texts.append(text)
                        labels.append(str(domain))

            except (json.JSONDecodeError, AttributeError) as e:
                print(f"Error loading {json_file.name}: {e}")
                continue

        print(f"domain分类数据: {len(texts)} 个样本")
        return texts, labels

    def prepare_experiment_text(self, item: dict) -> str:
        """
        拼接实验相关的字段作为文本特征
        Concatenate experiment-related fields as text features

        参数 Parameters:
            item: JSON数据项 - JSON data item

        返回 Returns:
            str: 拼接后的文本 - Concatenated text
        """
        parts = []

        # Experiment Name (最高权重)
        exp_name = item.get("experiment_name", "")
        if exp_name:
            parts.append(str(exp_name))

        # Evidence (高权重，最多3条)
        evidence = item.get("evidence", [])
        if isinstance(evidence, list):
            parts.extend(str(e) for e in evidence[:3])
        elif evidence:
            parts.append(str(evidence))

        # Method (中权重)
        method = item.get("method", "")
        if method:
            parts.append(str(method))

        # Key Results (中权重，最多3条)
        key_results = item.get("key_results", [])
        if isinstance(key_results, list):
            parts.extend(str(r) for r in key_results[:3])
        elif key_results:
            parts.append(str(key_results))

        return " ".join(parts)

    def prepare_experiment_type_data(self) -> Tuple[List[str], List[str]]:
        """
        准备experiment_type分类数据（使用JSON字段拼接）
        Prepare experiment_type classification data using JSON field concatenation

        返回 Returns:
            Tuple[List[str], List[str]]: 文本列表和标签列表 - Text list and label list
        """
        texts = []
        labels = []

        for json_file in self.outputs_dir.glob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8', errors='ignore') as f:
                    data = json.load(f)

                # 处理数组格式或单个对象格式
                items = data if isinstance(data, list) else [data]

                for item in items:
                    text = self.prepare_experiment_text(item)
                    exp_type = item.get("experiment_type")

                    if text.strip() and exp_type:
                        texts.append(text)
                        labels.append(str(exp_type))

            except (json.JSONDecodeError, AttributeError) as e:
                print(f"Error loading {json_file.name}: {e}")
                continue

        print(f"experiment_type分类数据: {len(texts)} 个样本")
        return texts, labels

    def prepare_dataset_type_data(self) -> Tuple[List[str], List[str]]:
        """
        准备dataset_type分类数据
        Prepare dataset_type classification data

        返回 Returns:
            Tuple[List[str], List[str]]: 文本列表和标签列表 - Text list and label list
        """
        texts = []
        labels = []

        for json_file in self.outputs_dir.glob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8', errors='ignore') as f:
                    data = json.load(f)

                # 处理数组格式或单个对象格式
                items = data if isinstance(data, list) else [data]

                for item in items:
                    # 遍历数据集对象
                    datasets = item.get("datasets", [])
                    for dataset in datasets:
                        # 组合数据集文本
                        name = dataset.get("name", "")
                        description = dataset.get("description", "")
                        text = f"{name} {description}"

                        # 提取dataset_type标签
                        ds_type = dataset.get("dataset_type", "other")

                        if text.strip():
                            texts.append(text)
                            labels.append(str(ds_type))

            except (json.JSONDecodeError, AttributeError) as e:
                print(f"Error loading {json_file.name}: {e}")
                continue

        print(f"dataset_type分类数据: {len(texts)} 个样本")
        return texts, labels

    def save_processed_data(self, texts: List[str], labels: List[str],
                           field_name: str, test_size: float = 0.2):
        """
        保存处理后的数据（划分训练集和测试集）
        Save processed data (split into train and test sets)

        参数 Parameters:
            texts: 文本列表 - Text list
            labels: 标签列表 - Label list
            field_name: 字段名 - Field name
            test_size: 测试集比例 - Test set ratio
        """
        from sklearn.model_selection import train_test_split

        # 统计每类样本数
        label_counts = Counter(labels)
        print(f"  类别分布: {dict(label_counts)}")

        # 确定是否使用分层划分（需要每类至少2个样本）
        use_stratify = len(set(labels)) > 1 and all(count >= 2 for count in label_counts.values())

        # 划分训练集和测试集
        X_train, X_test, y_train, y_test = train_test_split(
            texts, labels,
            test_size=test_size,
            random_state=42,
            stratify=labels if use_stratify else None
        )

        # 创建保存目录
        save_dir = self.processed_dir / field_name
        save_dir.mkdir(parents=True, exist_ok=True)

        # 保存训练数据
        with open(save_dir / "train.txt", "w", encoding="utf-8") as f:
            for text in X_train:
                f.write(text + "\n")

        with open(save_dir / "train_labels.txt", "w", encoding="utf-8") as f:
            for label in y_train:
                f.write(label + "\n")

        # 保存测试数据
        with open(save_dir / "test.txt", "w", encoding="utf-8") as f:
            for text in X_test:
                f.write(text + "\n")

        with open(save_dir / "test_labels.txt", "w", encoding="utf-8") as f:
            for label in y_test:
                f.write(label + "\n")

        print(f"保存数据到: {save_dir}")
        print(f"  训练集: {len(X_train)} 个样本")
        print(f"  测试集: {len(X_test)} 个样本")
        print(f"  标签类别: {len(set(labels))} 类: {set(labels)}")
        print(f"  分层划分: {'是' if use_stratify else '否'}")

    def prepare_all_fields(self):
        """
        准备所有字段的数据
        Prepare data for all fields
        """
        fields = ["domain", "experiment_type", "dataset_type"]

        for field in fields:
            print(f"\n{'='*60}")
            print(f"准备 {field} 数据")
            print('='*60)

            if field == "domain":
                texts, labels = self.prepare_domain_data()
            elif field == "experiment_type":
                texts, labels = self.prepare_experiment_type_data()
            elif field == "dataset_type":
                texts, labels = self.prepare_dataset_type_data()
            else:
                print(f"未知字段: {field}")
                continue

            if texts and labels:
                self.save_processed_data(texts, labels, field, test_size=0.2)
            else:
                print(f"警告: {field} 没有有效数据")


def main():
    """
    主函数 - Main function
    """
    # 设置路径
    outputs_dir = ML_CLASSIFICATION / "data" / "dataset2_raw" / "outputs"
    processed_dir = ML_CLASSIFICATION / "data" / "processed" / "dataset2"

    print(f"标注目录: {outputs_dir}")
    print(f"输出目录: {processed_dir}")
    print()

    # 检查输入目录
    if not outputs_dir.exists():
        print(f"错误: 标注目录不存在: {outputs_dir}")
        return

    json_count = len(list(outputs_dir.glob("*.json")))
    print(f"找到 {json_count} 个JSON文件")
    print()

    # 创建数据预处理器
    preparator = DataPreparatorDataset2(outputs_dir, processed_dir)

    # 准备所有字段的数据
    preparator.prepare_all_fields()

    print("\n" + "="*60)
    print("数据预处理完成！")
    print("="*60)


if __name__ == "__main__":
    main()