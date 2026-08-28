# ML Classification - 基于TF-IDF + 逻辑回归的枚举字段分类

## 项目概述

本项目使用TF-IDF特征工程和逻辑回归模型来提取论文的枚举字段（domain, experiment_type, dataset_type），替代原有的规则提取方法。

## 目录结构

```
ml_classification/
├── data/                          # 数据目录
│   ├── raw/                       # 原始数据
│   │   ├── corpus/                # 原始论文md文件（从bulk_extraction/corpus复制）
│   │   └── outputs/               # 原始LLM提取结果（从bulk_extraction/outputs/per_paper复制）
│   └── processed/                 # 处理后的数据
│       ├── domain/                # 领域数据
│       │   ├── train.txt
│       │   ├── train_labels.txt
│       │   ├── test.txt
│       │   └── test_labels.txt
│       ├── experiment_type/       # 实验类型数据
│       │   ├── train.txt
│       │   ├── train_labels.txt
│       │   ├── test.txt
│       │   └── test_labels.txt
│       └── dataset_type/          # 数据集类型数据
│           ├── train.txt
│           ├── train_labels.txt
│           ├── test.txt
│           └── test_labels.txt
├── models/                        # 训练好的模型
│   ├── domain/                    # 领域模型
│   │   ├── vectorizer.pkl          # TF-IDF向量化器
│   │   ├── label_encoder.pkl       # 标签编码器
│   │   ├── model.pkl              # 逻辑回归模型
│   │   └── evaluation_report.json # 评估报告
│   ├── experiment_type/           # 实验类型模型
│   │   ├── vectorizer.pkl
│   │   ├── label_encoder.pkl
│   │   ├── model.pkl
│   │   └── evaluation_report.json
│   └── dataset_type/              # 数据集类型模型
│       ├── vectorizer.pkl
│       ├── label_encoder.pkl
│       ├── model.pkl
│       └── evaluation_report.json
├── scripts/                       # 脚本文件
│   ├── data_preparation.py        # 数据预处理脚本
│   ├── model_training.py          # 模型训练脚本
│   ├── model_evaluation.py        # 模型评估脚本
│   ├── predict.py                 # 预测脚本
│   └── expand_data.py             # 数据扩展脚本
└── src/                           # 源代码
    ├── __init__.py
    ├── preprocessing.py           # 文本预处理模块
    ├── tfidf_feature.py           # TF-IDF特征工程模块
    ├── logistic_regression.py     # 逻辑回归模块
    ├── postprocessing.py          # 后处理策略模块
    └── utils.py                   # 工具函数
```

## 快速开始

### 1. 数据扩展（可选）

```bash
# 从bulk_extraction复制更多数据
python scripts/expand_data.py
```

### 2. 数据准备

```bash
python scripts/data_preparation.py
```

### 3. 模型训练

```bash
# 训练所有模型
python scripts/model_training.py --field all

# 训练单个模型
python scripts/model_training.py --field domain
python scripts/model_training.py --field experiment_type
python scripts/model_training.py --field dataset_type
```

### 4. 模型评估

```bash
# 评估所有模型
python scripts/model_evaluation.py --field all

# 评估单个模型
python scripts/model_evaluation.py --field domain
```

### 5. 预测新论文

```bash
# 单论文预测
python scripts/predict.py --paper-id 5390b24320f70186a0ee6fb7

# 批量预测
python scripts/predict.py --batch --limit 20
```

## 模型性能（1000样本）

### Domain 分类
- **准确率**: 95.43%
- **类别数**: 5 (computer_science, environment, medicine, engineering, materials)
- **训练样本**: 786
- **测试样本**: 197
- **类别分布**: computer_science (964), environment (2), medicine (13), engineering (2), materials (2)

### Experiment Type 分类 (JSON字段拼接特征)
- **准确率**: 55.88% (vs MD文本 27.92%，提升100%)
- **类别数**: 12 (benchmark, comparison, empirical_study, other, survey, simulation, ablation, data_analysis, field_study, human_study, lab_experiment, case_study)
- **训练样本**: 1359
- **测试样本**: 340
- **类别分布**: benchmark (481), comparison (500), empirical_study (312), other (14), survey (83), simulation (57), ablation (192), data_analysis (14), field_study (4), human_study (20), lab_experiment (15), case_study (7)

**特征工程改进**:
- 使用JSON字段拼接：experiment_name + evidence + method + key_results
- 解决同论文多实验数据混淆问题
- 每个实验有独立文本特征

**各类别准确率**:
- ablation: 86.84% (vs 15.00%)
- survey: 88.24% (vs 73.33%)
- benchmark: 60.42% (vs 32.20%)
- comparison: 40.00% (vs 17.31%)
- empirical_study: 44.44% (vs 26.83%)
- 小类别改善明显: human_study/lab_experiment/field_study 达到100%

### 后处理策略（备选策略1）

针对 experiment_type 中 benchmark vs comparison 的混淆问题，提供基于规则的后处理策略：

**策略1: 基于置信度+关键词的智能修正**
- **规则**: 如果预测为 comparison 且置信度 < 0.6，且文本包含 "benchmark" 关键词，则改为 benchmark
- **效果**:
  - 总准确率: 56.76% (+0.88%)
  - Benchmark准确率: 64.58% (+4.17%)
  - Comparison准确率: 39.00% (-1.00%)
  - 修改样本: 9/340 (2.65%)

**使用方法**:
```python
from logistic_regression import LogisticRegressionClassifier

# 加载模型
classifier = LogisticRegressionClassifier()
classifier.load("models/experiment_type")

# 带后处理的预测
y_pred_post = classifier.predict_with_postprocessing(
    X_test,          # 特征矩阵
    test_texts,      # 原始文本列表
    strategy_name="strategy_1",  # 策略名称
    confidence_threshold=0.6    # 置信度阈值
)
```

**测试脚本**:
```bash
# 测试后处理策略
python scripts/test_postprocessing_integration.py
```

**策略详情**: 参见 `src/postprocessing.py`

### Dataset Type 分类
- **准确率**: 62.84%
- **类别数**: 15 (image, text, video, audio, sensor, medical, tabular, timeseries, multimodal, other, simulation, biological, chemical, industrial, material)
- **训练样本**: 3550
- **测试样本**: 888
- **类别分布**: image (2098), text (416), video (391), multimodal (492), other (372), sensor (124), tabular (114), audio (110), timeseries (83), simulation (104), medical (97), chemical (32), biological (2), industrial (2), material (1)

## 文本预处理策略

### Domain 分类
- 提取论文标题
- 提取论文摘要
- 标准化处理（小写、去除标点）

### Experiment Type 分类
- 提取论文标题
- 提取论文摘要
- 提取摘要的最后2句话
- 提取实验章节前200个词
- 标准化处理

### Dataset Type 分类
- 提取数据集名称
- 提取数据集描述
- 组合文本
- 标准化处理

## 特点

- ✅ 自动特征学习（TF-IDF）
- ✅ 无需手工维护特征词
- ✅ 轻量级模型（逻辑回归）
- ✅ 完全在CPU上运行
- ✅ 快速训练和推理
- ✅ 支持多字段分类
- ✅ 提供详细的评估报告

## 技术栈

- Python 3.8+
- scikit-learn
- numpy
- joblib

## 依赖安装

```bash
pip install scikit-learn numpy joblib
```

## 数据源

数据来自 `bulk_extraction` 目录：
- 原始数据源: 2880个JSON标注文件, 1440个MD文件
- 当前使用: 1000个样本
- 扩展脚本: `scripts/expand_data.py`