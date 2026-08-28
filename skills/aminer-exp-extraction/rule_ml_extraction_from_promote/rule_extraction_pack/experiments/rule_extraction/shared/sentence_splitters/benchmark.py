"""
句子切分方案对比 - Sentence Splitting Benchmark

对比不同句子切分方案的准确性
Compare accuracy of different sentence splitting methods
"""

from typing import List, Tuple
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.shared.utils import extract_first_n_sentences


# 测试样本 - Test samples
# 格式: (文本, 期望句子数, 描述) - Format: (text, expected_count, description)
TEST_SAMPLES = [
    (
        "Our method achieves SOTA results. It outperforms all baselines. Future work will focus on efficiency.",
        3,
        "简单句 Simple sentences"
    ),
    (
        "Dr. Smith proposed a new method. Prof. Johnson evaluated it. The results are promising.",
        3,
        "包含缩写 Contains abbreviations"
    ),
    (
        "The U.S. and U.K. signed a treaty. Fig. 1 shows the results. Sec. 3 discusses the method.",
        3,
        "多个缩写 Multiple abbreviations"
    ),
    (
        "Our approach has limitations. First, it is computationally expensive. Second, it requires large datasets.",
        3,
        "中文文本 Chinese text with English terms"
    ),
    (
        "This paper introduces a novel approach for image classification. We achieve state-of-the-art accuracy on ImageNet. The method is based on deep learning techniques.",
        3,
        "长句 Long sentences"
    ),
]


def count_sentences(text: str) -> int:
    """
    手动统计句子数（用于验证）
    Manually count sentences (for validation)
    """
    count = 0
    for char in text:
        if char in ".!?":
            count += 1
    return count


def test_regex_splitter(samples: List[Tuple[str, int, str]]) -> dict:
    """
    测试正则切分器
    Test regex splitter
    """
    results = {
        "method": "regex",
        "tests": []
    }

    for text, expected, description in samples:
        sentences = extract_first_n_sentences(text, n=10, method="regex")
        actual = len(sentences)

        results["tests"].append({
            "description": description,
            "expected": expected,
            "actual": actual,
            "correct": actual == expected,
            "sentences": sentences
        })

    results["accuracy"] = sum(1 for t in results["tests"] if t["correct"]) / len(results["tests"])
    return results


def test_nltk_splitter(samples: List[Tuple[str, int, str]]) -> dict:
    """
    测试NLTK切分器
    Test NLTK splitter
    """
    results = {
        "method": "nlk",
        "tests": []
    }

    for text, expected, description in samples:
        sentences = extract_first_n_sentences(text, n=10, method="nlk")
        actual = len(sentences)

        results["tests"].append({
            "description": description,
            "expected": expected,
            "actual": actual,
            "correct": actual == expected,
            "sentences": sentences
        })

    results["accuracy"] = sum(1 for t in results["tests"] if t["correct"]) / len(results["tests"])
    return results


def run_benchmark():
    """
    运行基准测试
    Run benchmark
    """
    print("=" * 60)
    print("句子切分方案基准测试 - Sentence Splitting Benchmark")
    print("=" * 60)

    # 测试正则方法 - Test regex method
    print("\n测试正则切分器 - Testing Regex Splitter...")
    regex_results = test_regex_splitter(TEST_SAMPLES)

    # 测试NLTK方法 - Test NLTK method
    print("\n测试NLTK切分器 - Testing NLTK Splitter...")
    nlk_results = test_nltk_splitter(TEST_SAMPLES)

    # 打印结果 - Print results
    print("\n" + "=" * 60)
    print("测试结果 - Test Results")
    print("=" * 60)

    print(f"\n正则切分器 Regex Splitter:")
    print(f"  准确率 Accuracy: {regex_results['accuracy']:.1%}")
    for test in regex_results["tests"]:
        status = "✓" if test["correct"] else "✗"
        print(f"  {status} {test['description']}: 期望{test['expected']}, 实际{test['actual']}")

    print(f"\nNLTK切分器 NLTK Splitter:")
    print(f"  准确率 Accuracy: {nlk_results['accuracy']:.1%}")
    for test in nlk_results["tests"]:
        status = "✓" if test["correct"] else "✗"
        print(f"  {status} {test['description']}: 期望{test['expected']}, 实际{test['actual']}")

    # 选择最佳方案 - Select best method
    print("\n" + "=" * 60)
    print("结论 - Conclusion")
    print("=" * 60)

    if regex_results["accuracy"] >= nlk_results["accuracy"]:
        best_method = "regex"
        print(f"推荐方案 Recommended: 正则切分器 (regex)")
        print(f"理由 Reason: 准确率 {regex_results['accuracy']:.1%} >= NLTK {nlk_results['accuracy']:.1%}")
    else:
        best_method = "nlk"
        print(f"推荐方案 Recommended: NLTK切分器 (nlk)")
        print(f"理由 Reason: 准确率 {nlk_results['accuracy']:.1%} > 正则 {regex_results['accuracy']:.1%}")

    return {
        "best_method": best_method,
        "regex_accuracy": regex_results["accuracy"],
        "nlk_accuracy": nlk_results["accuracy"]
    }


if __name__ == "__main__":
    result = run_benchmark()