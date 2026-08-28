"""
TF-IDF特征工程模块 - TF-IDF Feature Engineering Module

基于TF-IDF的文本特征提取和向量化
Text feature extraction and vectorization using TF-IDF

主要功能 Main Functions:
- 初始化TF-IDF向量化器
- 拟合文本向量化
- 特征选择和优化（卡方检验）
- 模型训练时提取特征
- 推理时提取特征
"""

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.feature_selection import chi2, SelectKBest
from sklearn.preprocessing import LabelEncoder
from typing import List, Tuple, Optional


class TfidfFeatureEngine:
    """TF-IDF特征引擎 - TF-IDF Feature Engine"""

    def __init__(self, max_features: int = 500, ngram_range: Tuple[int, int] = (1, 2),
                 use_chi2: bool = False, chi2_k: int = None):
        """
        初始化TF-IDF特征引擎
        Initialize TF-IDF feature engine

        伪代码 Pseudocode:
        1. 初始化TF-IDF向量化器
           Initialize TF-IDF vectorizer
        2. 设置参数
           Set parameters

        参数 Parameters:
            max_features: 最多特征数 - Maximum number of features
            ngram_range: n-gram范围 - N-gram range
            use_chi2: 是否使用卡方特征选择 - Whether to use chi-squared feature selection
            chi2_k: 卡方选择保留的特征数 - Number of features to keep with chi-squared
        """
        # 伪代码实现 - Pseudocode implementation
        self.max_features = max_features
        self.ngram_range = ngram_range
        self.use_chi2 = use_chi2
        self.chi2_k = chi2_k if chi2_k else max_features

        self.vectorizer = TfidfVectorizer(
            max_features=max_features,
            ngram_range=ngram_range,
            stop_words='english',
            min_df=2,              # 至少在2个文档中出现
            max_df=0.8,            # 最多在80%的文档中出现
            norm='l2'               # L2归一化
        )

        # 初始化卡方特征选择器
        self.selector = None
        if self.use_chi2:
            self.selector = SelectKBest(chi2, k=self.chi2_k)

    def fit_transform(self, texts: List[str], labels: Optional[List[str]] = None) -> any:
        """
        训练向量化器并转换文本为特征矩阵
        Train vectorizer and transform texts to feature matrix

        伪代码 Pseudocode:
        1. 输入文本列表
           Input text list
        2. 训练向量化器
           Train vectorizer on texts
        3. 如果启用卡方选择，应用特征选择
           If chi2 enabled, apply feature selection
        4. 转换文本为特征矩阵
           Transform texts to feature matrix
        5. 返回特征矩阵
           Return feature matrix

        参数 Parameters:
            texts: 文本列表 - Text list
            labels: 标签列表（用于卡方特征选择） - Label list (for chi2 feature selection)

        返回 Returns:
            any: 特征矩阵 - Feature matrix
        """
        # 伪代码实现 - Pseudocode implementation
        X = self.vectorizer.fit_transform(texts)

        # 应用卡方特征选择
        if self.use_chi2 and labels is not None:
            print(f"应用卡方特征选择: {X.shape[1]} -> {self.chi2_k} 个特征")
            X = self.selector.fit_transform(X, labels)
            print(f"实际保留特征数: {X.shape[1]}")
        elif self.use_chi2 and labels is None:
            print("警告: 启用了卡方特征选择但未提供标签，跳过特征选择")

        return X

    def transform(self, texts: List[str]) -> any:
        """
        使用已训练的向量化器转换文本为特征矩阵
        Transform texts to feature matrix using trained vectorizer

        伪代码 Pseudocode:
        1. 输入文本列表
           Input text list
        2. 使用训练好的向量化器转换
           Transform using trained vectorizer
        3. 如果启用卡方选择，应用特征选择
           If chi2 enabled, apply feature selection
        4. 返回特征矩阵
           Return feature matrix

        参数 Parameters:
            texts: 文本列表 - Text list

        返回 Returns:
            any: 特征矩阵 - Feature matrix
        """
        # 伪代码实现 - Pseudocode implementation
        if self.vectorizer is None:
            raise ValueError("Vectorizer not fitted. Call fit_transform first")

        X = self.vectorizer.transform(texts)

        # 应用卡方特征选择（必须与训练时一致）
        if self.use_chi2 and self.selector is not None:
            X = self.selector.transform(X)

        return X

    def get_vocabulary(self) -> dict:
        """
        获取学习到的词汇表
        Get learned vocabulary

        返回 Returns:
            dict: 词汇表 - Vocabulary dictionary
        """
        # 伪代码实现 - Pseudocode implementation
        if self.vectorizer is None:
            return {}

        return self.vectorizer.vocabulary_

    def get_selected_features(self) -> List[str]:
        """
        获取被卡方选择器选中的特征名称
        Get names of selected features by chi-squared selector

        返回 Returns:
            List[str]: 选中特征的名称列表 - List of selected feature names
        """
        # 伪代码实现 - Pseudocode implementation
        if self.selector is None:
            return []

        # 获取选中的特征索引
        selected_indices = self.selector.get_support(indices=True)

        # 获取词汇表
        vocabulary = self.get_vocabulary()
        idx2word = {v: k for k, v in vocabulary.items()}

        # 返回选中的特征名称
        return [idx2word[idx] for idx in sorted(selected_indices)]

    def get_feature_importance(self, model, n_top: int = 10) -> List[Tuple[str, float]]:
        """
        获取最重要的特征（词汇）及其重要性权重
        Get most important features (vocabularies) and their importance weights

        伪代码 Pseudocode:
        1. 获取模型的系数矩阵
           Get model coefficient matrix
        2. 如果使用了卡方选择，获取选中的特征
           If chi2 used, get selected features
        3. 对每个类别，找出权重最大的特征
           For each class, find features with highest weights
        4. 计算平均重要性（跨类别）
           Calculate average importance across classes
        5. 返回前n个最重要的特征
           Return top n important features

        参数 Parameters:
            model: 训练好的逻辑回归模型 - Trained logistic regression model
            n_top: 返回前几个特征 - Return top n features

        返回 Returns:
            List[Tuple[str, float]]: 特征名称和重要性 - Feature name and importance
        """
        # 伪代码实现 - Pseudocode implementation
        if model is None:
            return []

        # 获取模型的系数矩阵 (类别数 × 特征数)
        coefficients = model.coef_  # shape: (n_classes, n_features)

        # 计算每个特征的平均重要性（跨所有类别）
        # 使用绝对值然后平均
        feature_importance = np.abs(coefficients).mean(axis=0)  # 按行平均

        # 获取选中的特征名称
        if self.use_chi2:
            selected_features = self.get_selected_features()
            idx2word = {i: name for i, name in enumerate(selected_features)}
        else:
            vocabulary = self.get_vocabulary()
            idx2word = {v: k for k, v in vocabulary.items()}  # 反转：索引→词

        # 排序并获取前n个特征
        top_indices = feature_importance.argsort()[-n_top:][::-1]

        return [(idx2word[idx], feature_importance[idx]) for idx in top_indices]

    def save_model(self, path: str):
        """
        保存向量化器和特征选择器
        Save vectorizer and feature selector

        伪代码 Pseudocode:
        1. 将向量化器保存到指定路径
           Save vectorizer to specified path
        2. 如果有特征选择器，也保存
           If feature selector exists, save it too

        参数 Parameters:
            path: 保存路径 - Save path
        """
        # 伪代码实现 - Pseudocode implementation
        model_data = {
            'vectorizer': self.vectorizer,
            'selector': self.selector,
            'use_chi2': self.use_chi2,
            'chi2_k': self.chi2_k
        }
        joblib.dump(model_data, path)

    def load_model(self, path: str):
        """
        加载向量化器和特征选择器
        Load vectorizer and feature selector

        伪代码 Pseudocode:
        1. 从指定路径加载模型数据
           Load model data from specified path
        2. 检查数据格式（新格式是字典，旧格式是直接对象）
           Check data format (new format is dict, old format is direct object)
        3. 恢复向量化器和特征选择器
           Restore vectorizer and feature selector

        参数 Parameters:
            path: 加载路径 - Load path

        返回 Returns:
            None: 无返回值 - No return value
        """
        # 伪代码实现 - Pseudocode implementation
        model_data = joblib.load(path)

        # 兼容新旧格式
        if isinstance(model_data, dict):
            # 新格式：字典
            self.vectorizer = model_data['vectorizer']
            self.selector = model_data['selector']
            self.use_chi2 = model_data.get('use_chi2', False)
            self.chi2_k = model_data.get('chi2_k', 500)
        else:
            # 旧格式：直接是vectorizer对象
            self.vectorizer = model_data
            self.selector = None
            self.use_chi2 = False
            self.chi2_k = 500


class DatasetTypeFeatureEngine:
    """数据集类型特征引擎 - Dataset Type Feature Engine

专门处理数据集类型的特征提取
Specialized for dataset type feature extraction
"""

    def __init__(self, max_features: int = 300, ngram_range: Tuple[int, int] = (1, 2)):
        """
        初始化数据集类型特征引擎
        Initialize dataset type feature engine

        参数 Parameters:
            max_features: 最多特征数 - Maximum number of features
            ngram_range: n-gram范围 - N-gram range
        """
        # 伪代码实现 - Pseudocode implementation
        self.vectorizer = TfidfVectorizer(
            max_features=max_features,
            ngram_range=ngram_range,
            stop_words='english',
            min_df=1,              # 数据集类型可能只出现一次
            max_df=0.9,            # 数据集类型更稀疏，允许更大范围
            norm='l2'
        )

    def extract_features_from_datasets(self, datasets: List[dict]) -> Tuple[List[str], List[str]]:
        """
        从数据集对象列表中提取文本和标签
        Extract texts and labels from dataset objects list

        伪代码 Pseudocode:
        1. 初始化列表
           Initialize lists
        2. 遍历每个数据集对象
           Iterate through each dataset object
        3. 提取数据集名称和描述
           Extract dataset name and description
        4. 组合文本和标签
           Combine text and label
        5. 添加到列表中
           Add to lists
        6. 返回文本列表和标签列表
           Return text list and label list

        参数 Parameters:
            datasets: 数据集对象列表 - Dataset objects list

        返回 Returns:
            Tuple[List[str], List[str]]: 文本列表和标签列表 - Text list and label list
        """
        # 伪代码实现 - Pseudocode implementation
        texts = []
        labels = []

        for dataset in datasets:
            # 提取数据集名称作为主要特征
            name = dataset.get("name", "")
            description = dataset.get("description", "")

            # 如果描述太短，加上其他信息
            if len(description) < 20:
                type_str = dataset.get("dataset_type", "")
                aliases_str = ", ".join(dataset.get("aliases", []))
                text = f"{name} {type_str} {aliases_str}"
            else:
                text = f"{name} {description}"

            texts.append(text)

            # 提取数据集类型作为标签
            label = dataset.get("dataset_type", "other")
            labels.append(label)

        return texts, labels

    def fit_transform(self, datasets: List[dict]) -> Tuple[any, List[str]]:
        """
        训练向量化器并提取特征矩阵
        Train vectorizer and extract feature matrix

        伪代码 Pseudocode:
        1. 从数据集对象中提取文本和标签
           Extract texts and labels from dataset objects
        2. 训练向量化器
           Train vectorizer on texts
        3. 转换文本为特征矩阵
           Transform texts to feature matrix
        4. 编码标签
           Encode labels
        5. 返回特征矩阵和标签
           Return feature matrix and labels

        参数 Parameters:
            datasets: 数据集对象列表 - Dataset objects list

        返回 Returns:
            Tuple[any, List[str]]: 特征矩阵和标签 - Feature matrix and labels
        """
        # 伪代码实现 - Pseudocode implementation
        texts, labels = self.extract_features_from_datasets(datasets)

        # 训练向量化器并转换
        X = self.vectorizer.fit_transform(texts)

        # 编码标签
        label_encoder = LabelEncoder()
        y = label_encoder.fit_transform(labels)

        return X, y

    def transform(self, datasets: List[dict]) -> any:
        """
        使用已训练的向量化器提取特征矩阵
        Extract feature matrix using trained vectorizer

        伪代码 Pseudocode:
        1. 从数据集对象中提取文本
           Extract texts from dataset objects
        2. 使用训练好的向量化器转换
           Transform using trained vectorizer
        3. 返回特征矩阵
           Return feature matrix

        参数 Parameters:
            datasets: 数据集对象列表 - Dataset objects list

        返回 Returns:
            any: 特征矩阵 - Feature matrix
        """
        # 伪代码实现 - Pseudocode implementation
        texts, _ = self.extract_features_from_datasets(datasets)

        if self.vectorizer is None:
            raise ValueError("Vectorizer not fitted. Call fit_transform first")

        X = self.vectorizer.transform(texts)
        return X