"""
模型评估脚本 - Model Evaluation Script

评估已训练的TF-IDF + 逻辑回归模型性能
Evaluate trained TF-IDF + Logistic Regression model performance

主要功能 Main Functions:
- 加载训练好的模型
- 在测试集上评估模型性能
- 生成详细的评估报告
- 展示混淆矩阵
"""

import sys
import json
import numpy as np
from pathlib import Path
from collections import Counter
import argparse

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
ML_CLASSIFICATION = PROJECT_ROOT / "ml_classification"
sys.path.insert(0, str(ML_CLASSIFICATION / "src"))

from tfidf_feature import TfidfFeatureEngine
from logistic_regression import LogisticRegressionClassifier


class ModelEvaluator:
    """模型评估器 - Model Evaluator"""

    def __init__(self, processed_dir: Path, model_dir: Path):
        """
        初始化模型评估器
        Initialize model evaluator

        伪代码 Pseudocode:
        1. 设置处理后数据目录
           Set processed data directory
        2. 设置模型目录
           Set model directory

        参数 Parameters:
            processed_dir: 处理后数据目录 - Processed data directory
            model_dir: 模型目录 - Model directory
        """
        # 伪代码实现 - Pseudocode implementation
        self.processed_dir = processed_dir
        self.model_dir = model_dir

    def load_model(self, field_name: str) -> tuple:
        """
        加载训练好的模型
        Load trained model

        伪代码 Pseudocode:
        1. 创建分类器实例
           Create classifier instance
        2. 加载模型
           Load model
        3. 创建特征引擎实例
           Create feature engine instance
        4. 加载向量化器
           Load vectorizer
        5. 返回分类器和特征引擎
           Return classifier and feature engine

        参数 Parameters:
            field_name: 字段名 - Field name

        返回 Returns:
            tuple: (分类器, 特征引擎) - (classifier, feature engine)
        """
        # 伪代码实现 - Pseudocode implementation
        model_path = self.model_dir / field_name

        classifier = LogisticRegressionClassifier()
        classifier.load(str(model_path))

        feature_engine = TfidfFeatureEngine()
        feature_engine.load_model(str(model_path / "vectorizer.pkl"))

        return classifier, feature_engine

    def load_test_data(self, field_name: str) -> tuple:
        """
        加载测试数据
        Load test data

        伪代码 Pseudocode:
        1. 构建文件路径
           Build file paths
        2. 读取测试文本
           Read test texts
        3. 读取测试标签
           Read test labels
        4. 返回数据
           Return data

        参数 Parameters:
            field_name: 字段名 - Field name

        返回 Returns:
            tuple: (测试文本, 测试标签) - (test texts, test labels)
        """
        # 伪代码实现 - Pseudocode implementation
        field_dir = self.processed_dir / field_name

        with open(field_dir / "test.txt", "r", encoding="utf-8") as f:
            test_texts = [line.strip() for line in f if line.strip()]

        with open(field_dir / "test_labels.txt", "r", encoding="utf-8") as f:
            test_labels = [line.strip() for line in f if line.strip()]

        return test_texts, test_labels

    def evaluate_model(self, field_name: str, save_report: bool = True) -> dict:
        """
        评估指定字段的模型
        Evaluate model for specified field

        伪代码 Pseudocode:
        1. 加载模型
           Load model
        2. 加载测试数据
           Load test data
        3. 转换测试文本
           Transform test texts
        4. 进行预测
           Make predictions
        5. 计算准确率
           Calculate accuracy
        6. 计算每类准确率
           Calculate per-class accuracy
        7. 计算精确率、召回率、F1
           Calculate precision, recall, F1
        8. 生成混淆矩阵
           Generate confusion matrix
        9. 保存评估报告
           Save evaluation report
        10. 返回评估结果
            Return evaluation result

        参数 Parameters:
            field_name: 字段名 - Field name
            save_report: 是否保存报告 - Whether to save report

        返回 Returns:
            dict: 评估结果 - Evaluation result
        """
        # 伪代码实现 - Pseudocode implementation
        print(f"\n{'='*60}")
        print(f"评估 {field_name} 模型")
        print('='*60)

        # 加载模型
        print("\n加载模型...")
        classifier, feature_engine = self.load_model(field_name)

        # 加载测试数据
        print("加载测试数据...")
        test_texts, test_labels = self.load_test_data(field_name)
        print(f"测试集样本数: {len(test_texts)}")
        print(f"测试集类别: {set(test_labels)}")

        # 转换测试文本
        print("转换测试文本...")
        X_test = feature_engine.transform(test_texts)

        # 进行预测
        print("进行预测...")
        y_pred = classifier.predict_class_names(X_test)
        y_proba = classifier.predict_proba(X_test)
        y_pred_indices, confidences = classifier.predict_with_confidence(X_test)

        # 计算准确率
        accuracy = sum(1 for yt, yp in zip(test_labels, y_pred) if yt == yp) / len(test_labels)

        # 计算每类准确率
        label_counts = Counter(test_labels)
        per_class_accuracy = {}
        per_class_metrics = {}

        print(f"\n{'='*60}")
        print(f"准确率: {accuracy:.4f} ({accuracy*100:.2f}%)")
        print('='*60)

        # 计算每类的精确率、召回率、F1
        from sklearn.metrics import precision_recall_fscore_support

        precision, recall, f1, support = precision_recall_fscore_support(
            test_labels, y_pred, average=None, zero_division=0
        )

        classes = sorted(set(test_labels))

        print(f"\n{'类别':<20} {'准确率':<10} {'精确率':<10} {'召回率':<10} {'F1':<10} {'支持数':<10}")
        print("-" * 70)

        for i, label in enumerate(classes):
            if i < len(precision):
                mask = [yt == label for yt in test_labels]
                correct = sum(1 for yt, yp in zip(test_labels, y_pred) if yt == yp and yt == label)
                acc = correct / sum(mask) if sum(mask) > 0 else 0

                per_class_accuracy[label] = acc
                per_class_metrics[label] = {
                    "accuracy": acc,
                    "precision": precision[i],
                    "recall": recall[i],
                    "f1": f1[i],
                    "support": support[i]
                }

                print(f"{label:<20} {acc:<10.4f} {precision[i]:<10.4f} {recall[i]:<10.4f} {f1[i]:<10.4f} {support[i]:<10}")

        # 生成混淆矩阵
        print(f"\n混淆矩阵:")
        from sklearn.metrics import confusion_matrix
        cm = confusion_matrix(test_labels, y_pred, labels=classes)
        print("     " + " ".join(f"{c[:10]:>10}" for c in classes))
        for i, true_class in enumerate(classes):
            print(f"{true_class[:4]:<5}" + " ".join(f"{cm[i][j]:>10}" for j in range(len(classes))))

        # 分析错误预测
        print(f"\n错误预测分析:")
        print("-" * 60)
        error_count = sum(1 for yt, yp in zip(test_labels, y_pred) if yt != yp)
        print(f"总错误数: {error_count}/{len(test_labels)} ({error_count/len(test_labels)*100:.2f}%)")

        # 按错误类型统计
        error_types = Counter()
        for yt, yp in zip(test_labels, y_pred):
            if yt != yp:
                error_types[(yt, yp)] += 1

        print("\n最常见的错误类型:")
        for (true_label, pred_label), count in error_types.most_common(5):
            print(f"  {true_label} -> {pred_label}: {count} 次")

        # 计算置信度分布
        print(f"\n置信度分布:")
        print(f"  平均置信度: {confidences.mean():.4f}")
        print(f"  最低置信度: {confidences.min():.4f}")
        print(f"  最高置信度: {confidences.max():.4f}")
        print(f"  置信度<0.5: {(confidences < 0.5).sum()} 个样本")
        print(f"  置信度<0.7: {(confidences < 0.7).sum()} 个样本")
        print(f"  置信度<0.9: {(confidences < 0.9).sum()} 个样本")

        # 保存评估报告
        report = {
            "field_name": field_name,
            "accuracy": float(accuracy),
            "n_samples": len(test_texts),
            "n_classes": len(classes),
            "classes": list(classes),
            "per_class_metrics": {
                k: {
                    "accuracy": float(v["accuracy"]),
                    "precision": float(v["precision"]),
                    "recall": float(v["recall"]),
                    "f1": float(v["f1"]),
                    "support": int(v["support"])
                }
                for k, v in per_class_metrics.items()
            },
            "confusion_matrix": cm.tolist(),
            "error_count": error_count,
            "error_rate": error_count / len(test_texts),
            "confidence_stats": {
                "mean": float(confidences.mean()),
                "min": float(confidences.min()),
                "max": float(confidences.max()),
                "n_below_0_5": int((confidences < 0.5).sum()),
                "n_below_0_7": int((confidences < 0.7).sum()),
                "n_below_0_9": int((confidences < 0.9).sum()),
            }
        }

        if save_report:
            report_dir = self.model_dir / field_name
            report_dir.mkdir(parents=True, exist_ok=True)
            report_path = report_dir / "evaluation_report.json"
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            print(f"\n评估报告已保存到: {report_path}")

        return report

    def evaluate_all_models(self, save_report: bool = True) -> dict:
        """
        评估所有字段的模型
        Evaluate models for all fields

        伪代码 Pseudocode:
        1. 定义字段列表
           Define field list
        2. 遍历字段
           Iterate through fields
        3. 评估模型
           Evaluate model
        4. 保存结果
           Save result
        5. 返回所有结果
           Return all results
        """
        # 伪代码实现 - Pseudocode implementation
        fields = ["domain", "experiment_type", "dataset_type"]
        results = {}

        for field in fields:
            try:
                result = self.evaluate_model(field, save_report)
                results[field] = result
            except FileNotFoundError as e:
                print(f"警告: {field} 模型文件不存在，跳过评估")
                print(f"  错误: {e}")
                continue
            except Exception as e:
                print(f"警告: {field} 评估失败: {e}")
                continue

        # 汇总结果
        print(f"\n{'='*60}")
        print("评估结果汇总")
        print('='*60)
        for field_name, result in results.items():
            print(f"\n{field_name}:")
            print(f"  准确率: {result['accuracy']:.4f} ({result['accuracy']*100:.2f}%)")
            print(f"  类别数: {result['n_classes']}")
            print(f"  错误率: {result['error_rate']:.4f} ({result['error_rate']*100:.2f}%)")

        return results


def main():
    """
    主函数 - Main function
    """
    parser = argparse.ArgumentParser(description="评估TF-IDF + 逻辑回归模型性能")
    parser.add_argument("--field", type=str, choices=["domain", "experiment_type", "dataset_type", "all"],
                       default="all", help="要评估的字段 (默认: all)")
    parser.add_argument("--no-save", action="store_true", help="不保存评估报告")

    args = parser.parse_args()

    # 设置路径
    processed_dir = ML_CLASSIFICATION / "data" / "processed"
    model_dir = ML_CLASSIFICATION / "models"

    print(f"数据目录: {processed_dir}")
    print(f"模型目录: {model_dir}")
    print()

    # 创建模型评估器
    evaluator = ModelEvaluator(processed_dir, model_dir)

    # 评估模型
    if args.field == "all":
        results = evaluator.evaluate_all_models(save_report=not args.no_save)
    else:
        result = evaluator.evaluate_model(args.field, save_report=not args.no_save)
        results = {args.field: result}

    print("\n" + "="*60)
    print("模型评估完成!")
    print("="*60)


if __name__ == "__main__":
    main()