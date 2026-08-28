"""
模型训练脚本 - Model Training Script

训练TF-IDF + 逻辑回归分类模型
Train TF-IDF + Logistic Regression classification models

主要功能 Main Functions:
- 加载预处理后的数据
- 训练TF-IDF向量化器
- 训练逻辑回归模型
- 保存训练好的模型
"""

import sys
from pathlib import Path
import argparse

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
ML_CLASSIFICATION = PROJECT_ROOT / "ml_classification"
sys.path.insert(0, str(ML_CLASSIFICATION / "src"))

from tfidf_feature import TfidfFeatureEngine
from logistic_regression import LogisticRegressionClassifier


class ModelTrainer:
    """模型训练器 - Model Trainer"""

    def __init__(self, processed_dir: Path, model_dir: Path):
        """
        初始化模型训练器
        Initialize model trainer

        伪代码 Pseudocode:
        1. 设置处理后数据目录
           Set processed data directory
        2. 设置模型保存目录
           Set model save directory
        3. 创建模型目录
           Create model directory

        参数 Parameters:
            processed_dir: 处理后数据目录 - Processed data directory
            model_dir: 模型保存目录 - Model save directory
        """
        # 伪代码实现 - Pseudocode implementation
        self.processed_dir = processed_dir
        self.model_dir = model_dir
        self.model_dir.mkdir(parents=True, exist_ok=True)

    def load_processed_data(self, field_name: str) -> tuple:
        """
        加载处理后的数据
        Load processed data

        伪代码 Pseudocode:
        1. 构建文件路径
           Build file paths
        2. 读取训练文本
           Read train texts
        3. 读取训练标签
           Read train labels
        4. 读取测试文本
           Read test texts
        5. 读取测试标签
           Read test labels
        6. 返回数据
           Return data

        参数 Parameters:
            field_name: 字段名 - Field name

        返回 Returns:
            tuple: (训练文本, 训练标签, 测试文本, 测试标签) - (train texts, train labels, test texts, test labels)
        """
        # 伪代码实现 - Pseudocode implementation
        field_dir = self.processed_dir / field_name

        # 读取训练数据
        with open(field_dir / "train.txt", "r", encoding="utf-8", errors="ignore") as f:
            train_texts = [line.rstrip('\n') for line in f]

        with open(field_dir / "train_labels.txt", "r", encoding="utf-8") as f:
            train_labels = [line.strip() for line in f]

        # 确保长度一致
        if len(train_texts) != len(train_labels):
            print(f"警告: 训练集文本({len(train_texts)})和标签({len(train_labels)})数量不一致")
            min_len = min(len(train_texts), len(train_labels))
            train_texts = train_texts[:min_len]
            train_labels = train_labels[:min_len]

        # 读取测试数据
        with open(field_dir / "test.txt", "r", encoding="utf-8", errors="ignore") as f:
            test_texts = [line.rstrip('\n') for line in f]

        with open(field_dir / "test_labels.txt", "r", encoding="utf-8") as f:
            test_labels = [line.strip() for line in f]

        # 确保长度一致
        if len(test_texts) != len(test_labels):
            print(f"警告: 测试集文本({len(test_texts)})和标签({len(test_labels)})数量不一致")
            min_len = min(len(test_texts), len(test_labels))
            test_texts = test_texts[:min_len]
            test_labels = test_labels[:min_len]

        print(f"加载 {field_name} 数据:")
        print(f"  训练集: {len(train_texts)} 个样本")
        print(f"  测试集: {len(test_texts)} 个样本")
        print(f"  类别数: {len(set(train_labels))} 类: {set(train_labels)}")

        return train_texts, train_labels, test_texts, test_labels

    def train_field_model(self, field_name: str, max_features: int = 500, c: float = 1.0):
        """
        训练指定字段的模型
        Train model for specified field

        伪代码 Pseudocode:
        1. 加载数据
           Load data
        2. 初始化TF-IDF特征引擎
           Initialize TF-IDF feature engine
        3. 训练向量化器并转换训练文本
           Train vectorizer and transform train texts
        4. 初始化逻辑回归分类器
           Initialize logistic regression classifier
        5. 训练分类器
           Train classifier
        6. 转换测试文本
           Transform test texts
        7. 在测试集上评估
           Evaluate on test set
        8. 保存模型
           Save model
        9. 返回结果
           Return result

        参数 Parameters:
            field_name: 字段名 - Field name
            max_features: 最大特征数 - Maximum features
            c: 正则化强度 - Regularization strength
        """
        # 伪代码实现 - Pseudocode implementation
        print(f"\n{'='*60}")
        print(f"开始训练 {field_name} 模型")
        print('='*60)

        # 加载数据
        train_texts, train_labels, test_texts, test_labels = self.load_processed_data(field_name)

        # 初始化TF-IDF特征引擎
        # 对于experiment_type，启用卡方特征选择
        use_chi2 = (field_name == "experiment_type")

        if use_chi2:
            # 策略：先提取更多特征（3000），然后用卡方筛选出1000个最好的
            max_features = 3000
            chi2_k = 1000
            print(f"\n启用卡方特征选择策略:")
            print(f"  TF-IDF提取特征数: {max_features}")
            print(f"  卡方筛选保留: {chi2_k}")

            feature_engine = TfidfFeatureEngine(
                max_features=max_features,
                use_chi2=True,
                chi2_k=chi2_k
            )
        else:
            feature_engine = TfidfFeatureEngine(max_features=max_features)

        # 训练向量化器并转换训练文本
        print("\n正在训练TF-IDF向量化器...")
        X_train = feature_engine.fit_transform(train_texts, train_labels if use_chi2 else None)

        # 转换测试文本
        X_test = feature_engine.transform(test_texts)

        print(f"最终特征维度: {X_train.shape[1]}")

        # 如果使用了卡方选择，显示选中的特征示例
        if use_chi2:
            selected = feature_engine.get_selected_features()[:10]
            print(f"卡方选中特征示例: {', '.join(selected[:5])}")

        # 初始化逻辑回归分类器
        classifier = LogisticRegressionClassifier(c=c, max_iter=1000)

        # 训练分类器
        print("\n正在训练逻辑回归模型...")
        classifier.fit(X_train, train_labels)

        # 在测试集上评估
        print("\n在测试集上评估...")
        y_pred = classifier.predict_class_names(X_test)

        # 计算准确率
        accuracy = sum(1 for yt, yp in zip(test_labels, y_pred) if yt == yp) / len(test_labels)

        # 计算每类准确率
        from collections import Counter
        label_counts = Counter(test_labels)
        per_class_accuracy = {}
        for label in set(test_labels):
            mask = [yt == label for yt in test_labels]
            correct = sum(1 for yt, yp in zip(test_labels, y_pred) if yt == yp and yt == label)
            per_class_accuracy[label] = correct / sum(mask) if sum(mask) > 0 else 0

        print(f"\n测试集准确率: {accuracy:.4f} ({accuracy*100:.2f}%)")
        print(f"\n各类准确率:")
        for label, acc in per_class_accuracy.items():
            count = label_counts[label]
            print(f"  {label}: {acc:.4f} ({acc*100:.2f}%) - {count} 样本")

        # 获取特征重要性
        print(f"\n特征重要性 (Top 10):")
        top_features = feature_engine.get_feature_importance(classifier.model, n_top=10)
        for feature, score in top_features:
            print(f"  {feature}: {score:.4f}")

        # 保存模型
        model_save_dir = self.model_dir / field_name
        model_save_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n保存模型到: {model_save_dir}")

        # 保存TF-IDF向量化器
        feature_engine.save_model(str(model_save_dir / "vectorizer.pkl"))

        # 保存分类器
        classifier.vectorizer = feature_engine  # 赋值整个TfidfFeatureEngine对象
        classifier.save(str(model_save_dir))

        print(f"[OK] {field_name} 模型训练完成!")

        return {
            "accuracy": accuracy,
            "per_class_accuracy": per_class_accuracy,
            "n_classes": len(set(train_labels)),
            "n_features": X_train.shape[1]
        }

    def train_all_models(self):
        """
        训练所有字段的模型
        Train models for all fields

        伪代码 Pseudocode:
        1. 定义字段列表
           Define field list
        2. 为每个字段设置参数
           Set parameters for each field
        3. 遍历字段
           Iterate through fields
        4. 训练模型
           Train model
        5. 保存结果
           Save result
        6. 返回所有结果
           Return all results
        """
        # 伪代码实现 - Pseudocode implementation
        fields = [
            {"name": "domain", "max_features": 500, "c": 1.0},
            {"name": "experiment_type", "max_features": 500, "c": 1.0},
            {"name": "dataset_type", "max_features": 300, "c": 1.0},
        ]

        results = {}

        for field_config in fields:
            field_name = field_config["name"]
            max_features = field_config["max_features"]
            c = field_config["c"]

            result = self.train_field_model(field_name, max_features, c)
            results[field_name] = result

        # 汇总结果
        print(f"\n{'='*60}")
        print("训练结果汇总")
        print('='*60)
        for field_name, result in results.items():
            print(f"\n{field_name}:")
            print(f"  准确率: {result['accuracy']:.4f} ({result['accuracy']*100:.2f}%)")
            print(f"  类别数: {result['n_classes']}")
            print(f"  特征数: {result['n_features']}")

        return results


def main():
    """
    主函数 - Main function
    """
    parser = argparse.ArgumentParser(description="训练TF-IDF + 逻辑回归分类模型")
    parser.add_argument("--field", type=str, choices=["domain", "experiment_type", "dataset_type", "all"],
                       default="all", help="要训练的字段 (默认: all)")
    parser.add_argument("--max-features", type=int, default=500, help="TF-IDF最大特征数")
    parser.add_argument("--c", type=float, default=1.0, help="逻辑回归正则化强度")

    args = parser.parse_args()

    # 设置路径
    processed_dir = ML_CLASSIFICATION / "data" / "processed"
    model_dir = ML_CLASSIFICATION / "models"

    print(f"数据目录: {processed_dir}")
    print(f"模型目录: {model_dir}")
    print()

    # 创建模型训练器
    trainer = ModelTrainer(processed_dir, model_dir)

    # 训练模型
    if args.field == "all":
        results = trainer.train_all_models()
    else:
        result = trainer.train_field_model(args.field, args.max_features, args.c)
        results = {args.field: result}

    print("\n" + "="*60)
    print("所有模型训练完成!")
    print("="*60)


if __name__ == "__main__":
    main()