"""
数据预处理脚本 - Data Preparation Script

为不同的分类任务设计相应的文本提取策略
Design text extraction strategies for different classification tasks

主要功能 Main Functions:
- 从标注数据中提取文本和标签
- 不同分类任务的文本预处理策略
- 数据集划分（训练集/测试集）
- 保存处理后的数据
"""

import json
import re
import sys
from pathlib import Path
from typing import List, Tuple, Dict

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
ML_CLASSIFICATION = PROJECT_ROOT / "ml_classification"
sys.path.insert(0, str(ML_CLASSIFICATION / "src"))


class DataPreparator:
    """数据预处理器 - Data Preparator"""

    def __init__(self, corpus_dir: Path, outputs_dir: Path, processed_dir: Path):
        """
        初始化数据预处理器
        Initialize data preparator

        伪代码 Pseudocode:
        1. 设置语料目录
           Set corpus directory
        2. 设置输出目录
           Set outputs directory
        3. 设置处理后数据目录
           Set processed data directory

        参数 Parameters:
            corpus_dir: 论文MD文件目录 - Paper MD files directory
            outputs_dir: 标注JSON文件目录 - Annotated JSON files directory
            processed_dir: 处理后数据保存目录 - Processed data save directory
        """
        # 伪代码实现 - Pseudocode implementation
        self.corpus_dir = corpus_dir
        self.outputs_dir = outputs_dir
        self.processed_dir = processed_dir
        self.processed_dir.mkdir(parents=True, exist_ok=True)

        # 导入预处理器
        from preprocessing import TextPreprocessor
        self.text_preprocessor = TextPreprocessor()

    def load_annotation_data(self) -> Dict[str, dict]:
        """
        加载所有标注数据
        Load all annotation data

        伪代码 Pseudocode:
        1. 初始化结果字典
           Initialize result dict
        2. 遍历JSON文件
           Iterate through JSON files
        3. 加载每个文件（可能是数组或单个对象）
           Load each file (may be array or single object)
        4. 按paper_id分组
           Group by paper_id
        5. 返回数据字典
           Return data dict

        返回 Returns:
            Dict[str, dict]: 按paper_id分组的数据 - Data grouped by paper_id
        """
        # 伪代码实现 - Pseudocode implementation
        data_by_id = {}

        for json_file in self.outputs_dir.glob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8', errors='ignore') as f:
                    data = json.load(f)

                # 处理数组格式（第一种格式）
                if isinstance(data, list):
                    for item in data:
                        paper_id = item.get("paper_id")
                        if paper_id:
                            data_by_id[paper_id] = item
                # 处理单个对象格式（第二种格式）
                elif isinstance(data, dict):
                    paper_id = data.get("paper_id")
                    if paper_id:
                        data_by_id[paper_id] = data

            except (json.JSONDecodeError, AttributeError) as e:
                print(f"Error loading {json_file.name}: {e}")
                continue

        return data_by_id

    def prepare_domain_data(self) -> Tuple[List[str], List[str]]:
        """
        准备domain分类数据
        Prepare domain classification data

        伪代码 Pseudocode:
        1. 加载标注数据
           Load annotation data
        2. 遍历每篇论文
           Iterate through each paper
        3. 加载MD文件
           Load MD file
        4. 使用domain预处理策略
           Use domain preprocessing strategy
        5. 提取domain标签
           Extract domain label
        6. 添加到列表
           Add to lists
        7. 返回文本和标签列表
           Return text and label lists

        返回 Returns:
            Tuple[List[str], List[str]]: 文本列表和标签列表 - Text list and label list
        """
        # 伪代码实现 - Pseudocode implementation
        texts = []
        labels = []
        data_by_id = self.load_annotation_data()

        print(f"加载了 {len(data_by_id)} 篇论文的标注数据")

        for paper_id, annotation in data_by_id.items():
            # 加载MD文件
            paper_md_path = self.corpus_dir / f"{paper_id}.md"
            if not paper_md_path.exists():
                print(f"警告: 未找到论文 {paper_id} 的MD文件")
                continue

            with open(paper_md_path, 'r', encoding='utf-8', errors='ignore') as f:
                paper_md = f.read()

            # 使用domain预处理策略（标题 + 摘要）
            text = self.text_preprocessor.preprocess_for_domain(paper_md)

            # 提取domain标签
            domain = annotation.get("domain")
            if not domain:
                continue

            texts.append(text)
            labels.append(str(domain))

        print(f"domain分类数据: {len(texts)} 个样本")
        return texts, labels

    def prepare_experiment_text(self, item: dict) -> str:
        """
        拼接实验相关的字段作为文本特征
        Concatenate experiment-related fields as text features

        伪代码 Pseudocode:
        1. 提取experiment_name
           Extract experiment_name
        2. 提取evidence
           Extract evidence
        3. 提取method
           Extract method
        4. 提取key_results
           Extract key_results
        5. 拼接所有部分
           Concatenate all parts

        参数 Parameters:
            item: JSON数据项 - JSON data item

        返回 Returns:
            str: 拼接后的文本 - Concatenated text
        """
        parts = []

        # 1. Experiment Name (最高权重)
        exp_name = item.get("experiment_name", "")
        if exp_name:
            parts.append(str(exp_name))

        # 2. Evidence (高权重)
        evidence = item.get("evidence", [])
        if isinstance(evidence, list):
            # 最多取3条evidence
            parts.extend(str(e) for e in evidence[:3])
        elif evidence:
            parts.append(str(evidence))

        # 3. Method (中权重)
        method = item.get("method", "")
        if method:
            parts.append(str(method))

        # 4. Key Results (中权重)
        key_results = item.get("key_results", [])
        if isinstance(key_results, list):
            # 最多取3条结果
            parts.extend(str(r) for r in key_results[:3])
        elif key_results:
            parts.append(str(key_results))

        return " ".join(parts)

    def prepare_experiment_type_data(self) -> Tuple[List[str], List[str]]:
        """
        准备experiment_type分类数据（使用JSON字段拼接）
        Prepare experiment_type classification data using JSON field concatenation

        伪代码 Pseudocode:
        1. 遍历JSON文件
           Iterate through JSON files
        2. 不再读取MD文件
           Don't read MD files
        3. 使用prepare_experiment_text拼接字段
           Use prepare_experiment_text to concatenate fields
        4. 提取experiment_type标签
           Extract experiment_type label
        5. 添加到列表
           Add to lists
        6. 返回文本和标签列表
           Return text and label lists

        返回 Returns:
            Tuple[List[str], List[str]]: 文本列表和标签列表 - Text list and label list
        """
        # 伪代码实现 - Pseudocode implementation
        texts = []
        labels = []

        # 直接遍历JSON文件，不使用load_annotation_data
        for json_file in self.outputs_dir.glob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8', errors='ignore') as f:
                    data = json.load(f)

                # 处理数组格式或单个对象格式
                items = data if isinstance(data, list) else [data]

                for item in items:
                    # 使用新的文本拼接方法
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

        伪代码 Pseudocode:
        1. 加载标注数据
           Load annotation data
        2. 遍历每篇论文
           Iterate through each paper
        3. 遍历每个数据集对象
           Iterate through each dataset object
        4. 组合数据集名称和描述
           Combine dataset name and description
        5. 提取dataset_type标签
           Extract dataset_type label
        6. 添加到列表
           Add to lists
        7. 返回文本和标签列表
           Return text and label lists

        返回 Returns:
            Tuple[List[str], List[str]]: 文本列表和标签列表 - Text list and label list
        """
        # 伪代码实现 - Pseudocode implementation
        texts = []
        labels = []
        data_by_id = self.load_annotation_data()

        print(f"加载了 {len(data_by_id)} 篇论文的标注数据")

        for paper_id, annotation in data_by_id.items():
            # 遍历数据集对象
            datasets = annotation.get("datasets", [])
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

        print(f"dataset_type分类数据: {len(texts)} 个样本")
        return texts, labels

    def save_processed_data(self, texts: List[str], labels: List[str],
                           field_name: str, test_size: float = 0.2):
        """
        保存处理后的数据（划分训练集和测试集）
        Save processed data (split into train and test sets)

        伪代码 Pseudocode:
        1. 统计每类样本数
           Count samples per class
        2. 确定是否使用分层划分
           Determine whether to use stratified split
        3. 划分训练集和测试集
           Split into train and test sets
        4. 创建保存目录
           Create save directory
        5. 保存训练文本
           Save train texts
        6. 保存训练标签
           Save train labels
        7. 保存测试文本
           Save test texts
        8. 保存测试标签
           Save test labels

        参数 Parameters:
            texts: 文本列表 - Text list
            labels: 标签列表 - Label list
            field_name: 字段名 - Field name
            test_size: 测试集比例 - Test set ratio
        """
        # 伪代码实现 - Pseudocode implementation
        from sklearn.model_selection import train_test_split
        from collections import Counter

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

        伪代码 Pseudocode:
        1. 准备domain数据
           Prepare domain data
        2. 保存domain数据
           Save domain data
        3. 准备experiment_type数据
           Prepare experiment_type data
        4. 保存experiment_type数据
           Save experiment_type data
        5. 准备dataset_type数据
           Prepare dataset_type data
        6. 保存dataset_type数据
           Save dataset_type data
        """
        # 伪代码实现 - Pseudocode implementation
        fields = ["domain", "experiment_type", "dataset_type"]

        for field in fields:
            print(f"\n{'='*50}")
            print(f"准备 {field} 数据")
            print('='*50)

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
    corpus_dir = ML_CLASSIFICATION / "data" / "raw" / "corpus"
    outputs_dir = ML_CLASSIFICATION / "data" / "raw" / "outputs"
    processed_dir = ML_CLASSIFICATION / "data" / "processed"

    print(f"语料目录: {corpus_dir}")
    print(f"标注目录: {outputs_dir}")
    print(f"输出目录: {processed_dir}")
    print()

    # 创建数据预处理器
    preparator = DataPreparator(corpus_dir, outputs_dir, processed_dir)

    # 准备所有字段的数据
    preparator.prepare_all_fields()

    print("\n" + "="*50)
    print("数据预处理完成！")
    print("="*50)


if __name__ == "__main__":
    main()