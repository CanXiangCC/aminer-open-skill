"""
dataset_type独立测试
"""
import sys
from pathlib import Path
from collections import Counter
import time

PROJECT_ROOT = Path(__file__).parent.parent.parent
ML_CLASSIFICATION = PROJECT_ROOT / "ml_classification"
sys.path.insert(0, str(ML_CLASSIFICATION / "src"))

from tfidf_feature import TfidfFeatureEngine
from logistic_regression import LogisticRegressionClassifier

def test_dataset_type(feature_type: str):
    data_dir = ML_CLASSIFICATION / "data" / "comparison_md_vs_json" / f"dataset_type_{feature_type}"

    # 加载数据
    train_txt = data_dir / "train.txt"
    train_labels = data_dir / "train_labels.txt"
    test_txt = data_dir / "test.txt"
    test_labels = data_dir / "test_labels.txt"

    with open(train_txt, 'r', encoding='utf-8', errors='ignore') as f:
        train_texts = [line.rstrip('\n') for line in f]
    with open(train_labels, 'r', encoding='utf-8') as f:
        train_labels = [line.strip() for line in f]
    with open(test_txt, 'r', encoding='utf-8', errors='ignore') as f:
        test_texts = [line.rstrip('\n') for line in f]
    with open(test_labels, 'r', encoding='utf-8') as f:
        test_labels = [line.strip() for line in f]

    print(f"{feature_type} 数据:")
    print(f"  训练: {len(train_texts)} 测试: {len(test_texts)} 类别: {len(set(train_labels))}")

    # 检查样本数是否匹配
    if len(train_texts) != len(train_labels):
        print(f"警告: 训练文本({len(train_texts)})和标签({len(train_labels)})数量不一致")

    if len(test_texts) != len(test_labels):
        print(f"警告: 测试文本({len(test_texts)})和标签({len(test_labels)})数量不一致")

    # 特征提取
    print(f"\n提取TF-IDF特征...")
    feature_engine = TfidfFeatureEngine(max_features=2000)
    X_train = feature_engine.fit_transform(train_texts, train_labels)
    X_test = feature_engine.transform(test_texts)
    print(f"特征维度: {X_train.shape[1]}")

    # 训练
    print(f"\n训练模型...")
    classifier = LogisticRegressionClassifier(c=1.0, max_iter=1000)
    start = time.time()
    classifier.fit(X_train, train_labels)
    train_time = time.time() - start
    print(f"训练时间: {train_time:.2f}秒")

    # 预测
    print(f"\n预测...")
    y_pred = classifier.predict_class_names(X_test)

    # 计算准确率
    accuracy = sum(1 for yt, yp in zip(test_labels, y_pred) if yt == yp) / len(test_labels)

    print(f"\n准确率: {accuracy:.4f} ({accuracy*100:.2f}%)")

    # 每类准确率
    label_counts = Counter(test_labels)
    print(f"\n各类准确率:")
    for label in sorted(set(test_labels)):
        mask = [yt == label for yt in test_labels]
        correct = sum(1 for yt, yp in zip(test_labels, y_pred) if yt == yp and yt == label)
        total = sum(mask)
        if total > 0:
            acc = correct / total
            print(f"  {label}: {acc:.4f} ({acc*100:.2f}%) - {total}样本")

    return accuracy

if __name__ == "__main__":
    print("="*60)
    print("Dataset Type 特征对比测试")
    print("="*60)

    json_acc = test_dataset_type("json")
    md_acc = test_dataset_type("md")

    diff = md_acc - json_acc
    print(f"\n对比结果:")
    print(f"JSON: {json_acc:.4f} ({json_acc*100:.2f}%)")
    print(f"MD:   {md_acc:.4f} ({md_acc*100:.2f}%)")
    print(f"差异: {diff:.4f} ({diff*100:.2f}%) {'[BETTER]' if diff > 0 else '[WORSE]'}")