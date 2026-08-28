"""
预测脚本 - Prediction Script

使用训练好的模型对新论文进行预测
Use trained models to predict on new papers

主要功能 Main Functions:
- 加载训练好的模型
- 预测新论文的字段值
- 支持单论文预测和批量预测
"""

import sys
import json
from pathlib import Path
import argparse

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
ML_CLASSIFICATION = PROJECT_ROOT / "ml_classification"
sys.path.insert(0, str(ML_CLASSIFICATION / "src"))

from tfidf_feature import TfidfFeatureEngine
from logistic_regression import LogisticRegressionClassifier
from preprocessing import TextPreprocessor


class Predictor:
    """预测器 - Predictor"""

    def __init__(self, corpus_dir: Path, model_dir: Path, use_postprocessing: bool = False, strategy: str = "strategy_1"):
        """
        初始化预测器
        Initialize predictor

        伪代码 Pseudocode:
        1. 设置语料目录
           Set corpus directory
        2. 设置模型目录
           Set model directory
        3. 初始化文本预处理器
           Initialize text preprocessor
        4. 缓存已加载的模型
           Cache loaded models
        5. 设置后处理选项
           Set post-processing options

        参数 Parameters:
            corpus_dir: 论文MD文件目录 - Paper MD files directory
            model_dir: 模型目录 - Model directory
            use_postprocessing: 是否启用后处理 - Whether to use post-processing
            strategy: 后处理策略名称 - Post-processing strategy name
        """
        # 伪代码实现 - Pseudocode implementation
        self.corpus_dir = corpus_dir
        self.model_dir = model_dir
        self.text_preprocessor = TextPreprocessor()
        self.models = {}  # 缓存已加载的模型
        self.use_postprocessing = use_postprocessing
        self.strategy = strategy

    def load_field_model(self, field_name: str) -> tuple:
        """
        加载指定字段的模型
        Load model for specified field

        伪代码 Pseudocode:
        1. 检查模型是否已缓存
           Check if model is cached
        2. 如果已缓存，直接返回
           If cached, return directly
        3. 创建分类器实例
           Create classifier instance
        4. 加载模型
           Load model
        5. 创建特征引擎实例
           Create feature engine instance
        6. 加载向量化器
           Load vectorizer
        7. 缓存模型
           Cache model
        8. 返回模型
           Return model

        参数 Parameters:
            field_name: 字段名 - Field name

        返回 Returns:
            tuple: (分类器, 特征引擎) - (classifier, feature engine)
        """
        # 伪代码实现 - Pseudocode implementation
        if field_name in self.models:
            return self.models[field_name]

        model_path = self.model_dir / field_name

        classifier = LogisticRegressionClassifier()
        classifier.load(str(model_path))

        feature_engine = TfidfFeatureEngine()
        feature_engine.load_model(str(model_path / "vectorizer.pkl"))

        self.models[field_name] = (classifier, feature_engine)
        return classifier, feature_engine

    def preprocess_text(self, paper_md: str, field_name: str) -> str:
        """
        根据字段类型预处理文本
        Preprocess text based on field type

        伪代码 Pseudocode:
        1. 根据字段名选择预处理策略
           Select preprocessing strategy based on field name
        2. 返回预处理后的文本
           Return preprocessed text

        参数 Parameters:
            paper_md: 论文markdown文本 - Paper markdown text
            field_name: 字段名 - Field name

        返回 Returns:
            str: 预处理后的文本 - Preprocessed text
        """
        # 伪代码实现 - Pseudocode implementation
        if field_name == "domain":
            return self.text_preprocessor.preprocess_for_domain(paper_md)
        elif field_name == "experiment_type":
            return self.text_preprocessor.preprocess_for_experiment_type(paper_md)
        else:
            # 通用预处理
            return paper_md[:500].lower()

    def predict_field(self, paper_md: str, field_name: str) -> dict:
        """
        预测指定字段的值
        Predict value for specified field

        伪代码 Pseudocode:
        1. 加载模型
           Load model
        2. 预处理文本
           Preprocess text
        3. 转换文本为特征
           Transform text to features
        4. 进行预测
           Make prediction
        5. 获取预测概率
           Get prediction probabilities
        6. 如果启用后处理，应用后处理策略
           If post-processing enabled, apply post-processing strategy
        7. 返回预测结果
           Return prediction result

        参数 Parameters:
            paper_md: 论文markdown文本 - Paper markdown text
            field_name: 字段名 - Field name

        返回 Returns:
            dict: 预测结果 - Prediction result
        """
        # 伪代码实现 - Pseudocode implementation
        classifier, feature_engine = self.load_field_model(field_name)

        # 预处理文本
        processed_text = self.preprocess_text(paper_md, field_name)

        # 转换为特征
        X = feature_engine.transform([processed_text])

        # 根据是否启用后处理选择预测方法
        if self.use_postprocessing and hasattr(classifier, 'predict_with_postprocessing'):
            # 带后处理的预测
            y_pred = classifier.predict_with_postprocessing(
                X,
                [processed_text],
                strategy_name=self.strategy
            )[0]
        else:
            # 普通预测
            y_pred = classifier.predict_class_names(X)[0]

        # 获取预测概率（用于输出）
        y_proba = classifier.predict_proba(X)[0]
        y_pred_indices, confidences = classifier.predict_with_confidence(X)

        # 获取所有类别的概率
        class_names = classifier.label_encoder.classes_
        class_probs = {name: float(prob) for name, prob in zip(class_names, y_proba)}

        # 排序
        sorted_probs = sorted(class_probs.items(), key=lambda x: x[1], reverse=True)

        result = {
            "field": field_name,
            "prediction": y_pred,
            "confidence": float(confidences[0]),
            "all_probs": class_probs,
            "top_predictions": [{"class": name, "probability": prob} for name, prob in sorted_probs[:3]]
        }

        # 标记是否使用了后处理
        if self.use_postprocessing:
            result["postprocessing"] = {
                "enabled": True,
                "strategy": self.strategy
            }

        return result

    def predict_paper(self, paper_id: str, fields: list = None) -> dict:
        """
        预测论文的所有字段
        Predict all fields for a paper

        伪代码 Pseudocode:
        1. 加载论文MD文件
           Load paper MD file
        2. 如果指定了字段，只预测这些字段
           If fields specified, only predict those
        3. 否则预测所有字段
           Otherwise predict all fields
        4. 返回预测结果
           Return prediction result

        参数 Parameters:
            paper_id: 论文ID - Paper ID
            fields: 字段列表 - Field list (None表示所有字段)

        返回 Returns:
            dict: 预测结果 - Prediction result
        """
        # 伪代码实现 - Pseudocode implementation
        # 加载论文MD文件
        paper_md_path = self.corpus_dir / f"{paper_id}.md"

        if not paper_md_path.exists():
            return {
                "paper_id": paper_id,
                "error": f"论文文件不存在: {paper_md_path}"
            }

        with open(paper_md_path, 'r', encoding='utf-8', errors='ignore') as f:
            paper_md = f.read()

        # 提取标题和摘要（用于输出）
        text_preprocessor = TextPreprocessor()
        title = text_preprocessor.extract_title(paper_md)
        abstract = text_preprocessor.extract_abstract(paper_md)

        # 确定要预测的字段
        if fields is None:
            fields = ["domain", "experiment_type"]
            # dataset_type需要数据集描述，暂不处理

        # 预测各字段
        predictions = {}
        for field in fields:
            try:
                result = self.predict_field(paper_md, field)
                predictions[field] = result
            except Exception as e:
                predictions[field] = {"error": str(e)}

        return {
            "paper_id": paper_id,
            "title": title,
            "abstract": abstract[:200] + "..." if len(abstract) > 200 else abstract,
            "predictions": predictions
        }

    def predict_batch(self, paper_ids: list = None, fields: list = None,
                     output_file: str = None) -> list:
        """
        批量预测论文
        Batch predict papers

        伪代码 Pseudocode:
        1. 如果未指定论文ID，获取所有论文
           If paper IDs not specified, get all papers
        2. 遍历论文
           Iterate through papers
        3. 预测每篇论文
           Predict each paper
        4. 添加到结果列表
           Add to result list
        5. 如果指定了输出文件，保存结果
           If output file specified, save results
        6. 返回所有结果
           Return all results

        参数 Parameters:
            paper_ids: 论文ID列表 - Paper ID list (None表示所有论文)
            fields: 字段列表 - Field list
            output_file: 输出文件路径 - Output file path

        返回 Returns:
            list: 预测结果列表 - Prediction result list
        """
        # 伪代码实现 - Pseudocode implementation
        # 获取论文ID列表
        if paper_ids is None:
            paper_ids = [f.stem for f in self.corpus_dir.glob("*.md")]

        print(f"开始批量预测 {len(paper_ids)} 篇论文...")

        results = []
        for i, paper_id in enumerate(paper_ids):
            if (i + 1) % 10 == 0:
                print(f"处理进度: {i+1}/{len(paper_ids)}")

            result = self.predict_paper(paper_id, fields)
            results.append(result)

        # 保存结果
        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"\n预测结果已保存到: {output_file}")

        return results


def main():
    """
    主函数 - Main function
    """
    parser = argparse.ArgumentParser(description="使用训练好的模型进行预测")
    parser.add_argument("--paper-id", type=str, help="论文ID")
    parser.add_argument("--fields", type=str, nargs='+',
                       choices=["domain", "experiment_type", "dataset_type"],
                       help="要预测的字段 (默认: domain, experiment_type)")
    parser.add_argument("--batch", action="store_true", help="批量预测模式")
    parser.add_argument("--output", type=str, help="输出文件路径")
    parser.add_argument("--limit", type=int, default=None, help="批量预测时的论文数量限制")
    parser.add_argument("--postprocessing", action="store_true", help="启用后处理策略")
    parser.add_argument("--strategy", type=str, default="strategy_1",
                       help="后处理策略名称 (默认: strategy_1)")

    args = parser.parse_args()

    # 设置路径
    corpus_dir = ML_CLASSIFICATION / "data" / "raw" / "corpus"
    model_dir = ML_CLASSIFICATION / "models"

    print(f"语料目录: {corpus_dir}")
    print(f"模型目录: {model_dir}")

    if args.postprocessing:
        print(f"后处理策略: {args.strategy}")

    print()

    # 创建预测器
    predictor = Predictor(corpus_dir, model_dir, use_postprocessing=args.postprocessing, strategy=args.strategy)

    # 单论文预测
    if args.paper_id:
        result = predictor.predict_paper(args.paper_id, args.fields)

        if "error" in result:
            print(f"错误: {result['error']}")
            return

        print(f"论文ID: {result['paper_id']}")
        print(f"标题: {result['title']}")
        print(f"摘要: {result['abstract']}\n")

        print("预测结果:")
        for field, pred in result['predictions'].items():
            if "error" in pred:
                print(f"  {field}: 错误 - {pred['error']}")
            else:
                print(f"  {field}:")
                print(f"    预测: {pred['prediction']}")
                print(f"    置信度: {pred['confidence']:.4f}")
                if pred.get("postprocessing", {}).get("enabled", False):
                    print(f"    [后处理策略: {pred['postprocessing']['strategy']}]")
                print(f"    Top 3预测:")
                for top in pred['top_predictions']:
                    print(f"      - {top['class']}: {top['probability']:.4f}")

    # 批量预测
    elif args.batch:
        # 获取论文ID列表
        paper_ids = [f.stem for f in corpus_dir.glob("*.md")]
        if args.limit:
            paper_ids = paper_ids[:args.limit]

        results = predictor.predict_batch(paper_ids, args.fields, args.output)

        print("\n预测结果汇总:")
        for result in results:
            if "error" in result:
                continue

            print(f"\n{result['paper_id']}:")
            for field, pred in result['predictions'].items():
                if "error" in pred:
                    print(f"  {field}: 错误")
                else:
                    print(f"  {field}: {pred['prediction']} ({pred['confidence']:.4f})")

    else:
        print("请指定 --paper-id 或 --batch 参数")


if __name__ == "__main__":
    main()