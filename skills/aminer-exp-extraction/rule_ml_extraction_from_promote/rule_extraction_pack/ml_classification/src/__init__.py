"""
ML分类模块 - ML Classification Module

基于TF-IDF + 逻辑回归的枚举字段分类
Classification of enum fields using TF-IDF + Logistic Regression

核心模块 Core Modules:
- preprocessing: 文本预处理模块 - Text preprocessing module
- tfidf_feature: TF-IDF特征工程模块 - TF-IDF feature engineering module
- logistic_regression: 逻辑回归模块 - Logistic regression module
- utils: 工具函数 - Utility functions
"""

__version__ = "0.1.0"

from .preprocessing import TextPreprocessor
from .tfidf_feature import TfidfFeatureEngine
from .logistic_regression import LogisticRegressionClassifier
from .utils import load_json_data, save_model

__all__ = [
    "TextPreprocessor",
    "TfidfFeatureEngine",
    "LogisticRegressionClassifier",
    "load_json_data",
    "save_model"
]