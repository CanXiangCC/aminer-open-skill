"""
测试后处理策略集成 - Test Post-processing Strategy Integration

验证后处理策略与现有模型的集成是否正确工作
Verify post-processing strategy integration with existing model
"""

import sys
from pathlib import Path
import numpy as np

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
ML_CLASSIFICATION = PROJECT_ROOT / "ml_classification"
sys.path.insert(0, str(ML_CLASSIFICATION / "src"))

from tfidf_feature import TfidfFeatureEngine
from logistic_regression import LogisticRegressionClassifier
from postprocessing import STRATEGIES, list_strategies, get_strategy, apply_strategy_1


def test_postprocessing_module():
    """测试后处理模块功能"""
    print("=" * 60)
    print("测试后处理模块")
    print("=" * 60)

    # 1. 列出所有策略
    print(f"\n可用策略: {list_strategies()}")
    print(f"策略数量: {len(STRATEGIES)}")

    # 2. 获取策略详情
    strategy = get_strategy("strategy_1")
    print(f"\n策略1详情:")
    print(f"  名称: {strategy['name']}")
    print(f"  描述: {strategy['description']}")
    print(f"  性能: {strategy['performance']}")

    # 3. 测试单个样本处理
    print(f"\n测试单个样本处理:")
    text = "HQ-RAIN Benchmark and RE-RAIN Dataset Construction..."
    pred_label = "comparison"
    pred_proba = np.array([0.1, 0.16, 0.18, 0.05, 0.3, 0.21])  # comparison置信度0.18
    classes = np.array(['ablation', 'benchmark', 'comparison', 'empirical_study', 'survey', 'other'])

    result = apply_strategy_1(text, pred_label, pred_proba, classes, confidence_threshold=0.6)
    print(f"  文本: {text[:60]}...")
    print(f"  原始预测: {pred_label} (置信度: {pred_proba[2]:.2f})")
    print(f"  后处理预测: {result}")
    print(f"  预期结果: benchmark (因为comparison置信度低且文本包含benchmark)")


def test_model_integration():
    """测试模型集成"""
    print(f"\n{'='*60}")
    print("测试模型集成")
    print("="*60)

    processed_dir = ML_CLASSIFICATION / "data" / "processed" / "experiment_type"
    model_dir = ML_CLASSIFICATION / "models" / "experiment_type"

    # 检查模型是否存在
    if not model_dir.exists():
        print(f"模型目录不存在: {model_dir}")
        print("请先训练模型: python scripts/model_training.py --field experiment_type")
        return

    try:
        # 加载模型
        print(f"\n加载模型...")
        classifier = LogisticRegressionClassifier()
        classifier.load(str(model_dir))

        feature_engine = TfidfFeatureEngine()
        feature_engine.load_model(str(model_dir / "vectorizer.pkl"))

        print(f"  模型加载成功")
        print(f"  类别数: {len(classifier.label_encoder.classes_)}")
        print(f"  类别: {list(classifier.label_encoder.classes_)}")

        # 加载测试数据
        print(f"\n加载测试数据...")
        with open(processed_dir / "test.txt", "r", encoding="utf-8", errors="ignore") as f:
            test_texts = [line.rstrip('\n') for line in f]
        with open(processed_dir / "test_labels.txt", "r", encoding="utf-8") as f:
            test_labels = [line.strip() for line in f]

        print(f"  测试样本数: {len(test_texts)}")

        # 转换特征
        X_test = feature_engine.transform(test_texts)
        print(f"  特征维度: {X_test.shape[1]}")

        # 原始预测
        print(f"\n原始预测...")
        y_pred_raw = classifier.predict_class_names(X_test)
        raw_accuracy = sum(1 for yt, yp in zip(test_labels, y_pred_raw) if yt == yp) / len(test_labels)
        print(f"  准确率: {raw_accuracy:.4f} ({raw_accuracy*100:.2f}%)")

        # 带后处理的预测
        print(f"\n后处理预测 (strategy_1)...")
        y_pred_post = classifier.predict_with_postprocessing(X_test, test_texts)
        post_accuracy = sum(1 for yt, yp in zip(test_labels, y_pred_post) if yt == yp) / len(test_labels)
        print(f"  准确率: {post_accuracy:.4f} ({post_accuracy*100:.2f}%)")
        print(f"  提升: {post_accuracy - raw_accuracy:+.4f} ({(post_accuracy - raw_accuracy)*100:+.2f}%)")

        # 统计修改数量
        changes = sum(1 for r, p in zip(y_pred_raw, y_pred_post) if r != p)
        print(f"\n被修改的样本数: {changes} / {len(test_texts)} ({changes/len(test_texts)*100:.2f}%)")

        # 按类别分析
        from collections import defaultdict
        per_class = defaultdict(lambda: {"correct_raw": 0, "correct_post": 0, "total": 0})
        for true_label, pred_raw, pred_post in zip(test_labels, y_pred_raw, y_pred_post):
            per_class[true_label]["total"] += 1
            if true_label == pred_raw:
                per_class[true_label]["correct_raw"] += 1
            if true_label == pred_post:
                per_class[true_label]["correct_post"] += 1

        print(f"\n各类别准确率变化:")
        for label in sorted(per_class.keys()):
            if per_class[label]["total"] > 0:
                acc_raw = per_class[label]["correct_raw"] / per_class[label]["total"]
                acc_post = per_class[label]["correct_post"] / per_class[label]["total"]
                change = acc_post - acc_raw
                print(f"  {label}: {acc_post:.4f} ({change:+.4f})")

        print(f"\n{'='*60}")
        print("模型集成测试完成!")
        print("="*60)

    except FileNotFoundError as e:
        print(f"错误: 模型文件不存在")
        print(f"  {e}")
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()


def main():
    """主函数"""
    print("\n" + "="*60)
    print("后处理策略集成测试")
    print("="*60)

    # 测试后处理模块
    test_postprocessing_module()

    # 测试模型集成
    test_model_integration()

    print("\n" + "="*60)
    print("所有测试完成!")
    print("="*60)


if __name__ == "__main__":
    main()