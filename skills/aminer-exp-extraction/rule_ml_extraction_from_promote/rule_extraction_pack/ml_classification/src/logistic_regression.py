"""
逻辑回归分类器 - Logistic Regression Classifier

使用逻辑回归模型进行文本分类
Text classification using logistic regression

主要功能 Main Functions:
- 训练多分类逻辑回归模型
- 预测新文本的类别
- 获取预测概率
- 模型保存和加载
"""

import joblib
from typing import Any, Tuple, Optional, List
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report


class LogisticRegressionClassifier:
    """逻辑回归分类器 - Logistic Regression Classifier"""

    def __init__(self, multi_class: str = 'multinomial', c: float = 1.0, max_iter: int = 1000):
        """
        初始化逻辑回归分类器
        Initialize logistic regression classifier

        伪代码 Pseudocode:
        1. 初始化模型参数
           Initialize model parameters

        参数 Parameters:
            multi_class: 多分类策略 - Multi-class strategy
            c: 正则化强度 - Regularization strength
            max_iter: 最大迭代次数 - Maximum iterations
        """
        # 伪代码实现 - Pseudocode implementation
        self.model = LogisticRegression(
            multi_class=multi_class,
            C=c,
            max_iter=max_iter,
            solver='lbfgs',
            random_state=42,
            class_weight='balanced',
            n_jobs=1  # 使用单进程避免Windows兼容性问题
        )

        self.label_encoder = LabelEncoder()
        self.is_fitted = False

    def fit(self, X, y):
        """
        训练逻辑回归模型
        Train logistic regression model

        伪代码 Pseudocode:
        1. 编码标签
           Encode labels
        2. 训练模型
           Train model on features and labels
        3. 标记为已训练
           Mark as fitted

        参数 Parameters:
            X: 特征矩阵 - Feature matrix
            y: 标签数组 - Label array
        """
        # 伪代码实现 - Pseudocode implementation
        # 编码标签
        y_encoded = self.label_encoder.fit_transform(y)

        # 训练模型
        self.model.fit(X, y_encoded)

        # 标记为已训练
        self.is_fitted = True

    def predict(self, X) -> np.ndarray:
        """
        预测类别
        Predict classes

        伪代码 Pseudocode:
        1. 检查模型是否已训练
           Check if model is trained
        2. 如果未训练，抛出错误
           Raise error if not trained
        3. 使用训练好的模型预测
           Use trained model to predict
        4. 返回预测的类别（编码后的索引）
           Return predicted class indices

        参数 Parameters:
            X: 特征矩阵 - Feature matrix

        返回 Returns:
            np.ndarray: 预测的类别索引 - Predicted class indices
        """
        # 伪代码实现 - Pseudocode implementation
        if not self.is_fitted:
            raise ValueError("Model not trained. Call fit() first.")

        # 预测
        predictions = self.model.predict(X)

        return predictions

    def predict_proba(self, X) -> np.ndarray:
        """
        预测概率
        Predict probabilities

        伪代码 Pseudocode:
        1. 检查模型是否已训练
           Check if model is trained
        2. 如果未训练，抛出错误
           Raise error if not trained
        3. 使用训练好的模型预测概率
           Use trained model to predict probabilities
        4. 返回概率矩阵
           Return probability matrix

        参数 Parameters:
            X: 特征矩阵 - Feature matrix

        返回 Returns:
            np.ndarray: 概率矩阵 - Probability matrix
        """
        # 伪代码实现 - Pseudocode implementation
        if not self.is_fitted:
            raise ValueError("Model not trained. Call fit() first.")

        # 预测概率
        probabilities = self.model.predict_proba(X)

        return probabilities

    def predict_with_confidence(self, X) -> Tuple[np.ndarray, np.ndarray]:
        """
        预测类别和置信度
        Predict classes with confidence

        伪代码 Pseudocode:
        1. 检查模型是否已训练
           Check if model is trained
        2. 如果未训练，抛出错误
           Raise error if not trained
        3. 使用训练好的模型预测
           Use trained model to predict
        4. 计算最大概率作为置信度
           Calculate max probability as confidence
        5. 返回预测的类别和置信度
           Return predicted classes and confidences

        参数 Parameters:
            X: 特征矩阵 - Feature matrix

        返回 Returns:
            Tuple[np.ndarray, np.ndarray]: 预测类别和置信度 - Predicted classes and confidences
        """
        # 伪代码实现 - Pseudocode implementation
        if not self.is_fitted:
            raise ValueError("Model not trained. Call fit() first.")

        # 预测
        y_pred = self.model.predict(X)
        y_proba = self.model.predict_proba(X)

        # 计算置信度（最大概率）
        confidences = y_proba.max(axis=1)

        return y_pred, confidences

    def predict_class_names(self, X) -> np.ndarray:
        """
        预测类别名称
        Predict class names

        伪代码 Pseudocode:
        1. 检查模型是否已训练
           Check if model is trained
        2. 如果未训练，抛出错误
           Raise error if not trained
        3. 预测类别索引
           Predict class indices
        4. 将索引转换为类别名称
           Convert indices to class names
        5. 返回类别名称数组
           Return class names array

        参数 Parameters:
            X: 特征矩阵 - Feature matrix

        返回 Returns:
            np.ndarray: 类别名称数组 - Class names array
        """
        # 伪代码实现 - Pseudocode implementation
        if not self.is_fitted:
            raise ValueError("Model not trained. Call fit() first.")

        # 预测类别索引
        y_pred = self.model.predict(X)

        # 转换为类别名称
        y_class_names = self.label_encoder.inverse_transform(y_pred)

        return y_class_names

    def predict_with_postprocessing(
        self,
        X,
        texts: list,
        strategy_name: str = "strategy_1",
        **strategy_kwargs
    ) -> np.ndarray:
        """
        带后处理策略的预测
        Prediction with post-processing strategy

        伪代码 Pseudocode:
        1. 检查模型是否已训练
           Check if model is trained
        2. 获取原始预测
           Get original predictions
        3. 获取预测概率
           Get prediction probabilities
        4. 应用后处理策略
           Apply post-processing strategy
        5. 返回处理后的预测
           Return processed predictions

        参数 Parameters:
            X: 特征矩阵 - Feature matrix
            texts: 原始文本列表 - Original text list
            strategy_name: 策略名称 - Strategy name (默认: "strategy_1")
            **strategy_kwargs: 策略参数 - Strategy parameters

        返回 Returns:
            np.ndarray: 后处理后的类别名称数组 - Post-processed class names array

        示例 Example:
            >>> y_pred_post = classifier.predict_with_postprocessing(X_test, test_texts)
            >>> # 使用strategy_1 (基于置信度+关键词的智能修正)
        """
        # 伪代码实现 - Pseudocode implementation
        if not self.is_fitted:
            raise ValueError("Model not trained. Call fit() first.")

        # 获取原始预测和概率
        y_pred = self.predict_class_names(X)
        y_pred_proba = self.predict_proba(X)
        classes = self.label_encoder.classes_

        # 导入后处理模块
        try:
            from postprocessing import apply_postprocessing
            # 应用后处理策略
            y_pred_post = apply_postprocessing(
                texts=texts,
                pred_labels=y_pred.tolist(),
                pred_probas=y_pred_proba,
                classes=classes,
                strategy_name=strategy_name,
                **strategy_kwargs
            )
            return np.array(y_pred_post)
        except ImportError:
            print("警告: 无法导入后处理模块，返回原始预测")
            return y_pred

    def save(self, model_dir: str):
        """
        保存模型到指定目录
        Save model to specified directory

        伪代码 Pseudocode:
        1. 将向量化器保存
           Save vectorizer
        2. 将标签编码器保存
           Save label encoder
        3. 将模型保存
           Save model
        4. 所有文件保存到指定目录
           Save all files to specified directory

        参数 Parameters:
            model_dir: 模型保存目录 - Model save directory
        """
        # 伪代码实现 - Pseudocode implementation
        import os
        os.makedirs(model_dir, exist_ok=True)

        # 保存各个组件
        if hasattr(self, 'vectorizer') and self.vectorizer is not None:
            # 调用 TfidfFeatureEngine 的 save_model 方法
            self.vectorizer.save_model(f"{model_dir}/vectorizer.pkl")

        if hasattr(self, 'label_encoder') and self.label_encoder is not None:
            joblib.dump(self.label_encoder, f"{model_dir}/label_encoder.pkl")

        joblib.dump(self.model, f"{model_dir}/model.pkl")

    def load(self, model_dir: str):
        """
        从指定目录加载模型
        Load model from specified directory

        伪代码 Pseudocode:
        1. 加载向量化器
           Load vectorizer
        2. 加载标签编码器
           Load label encoder
        3. 加载模型
           Load model
        4. 标记为已训练
           Mark as fitted
        5. 返回加载的分类器
           Return loaded classifier

        参数 Parameters:
            model_dir: 模型目录 - Model directory

        返回 Returns:
            LogisticRegressionClassifier: 加载的分类器 - Loaded classifier
        """
        # 伪代码实现 - Pseudocode implementation
        import os

        # 加载向量化器（兼容新旧格式）
        vectorizer_data = joblib.load(f"{model_dir}/vectorizer.pkl")

        # 新格式：字典包含vectorizer和selector
        # 旧格式：直接是vectorizer对象
        if isinstance(vectorizer_data, dict):
            # 需要导入TfidfFeatureEngine来处理
            from tfidf_feature import TfidfFeatureEngine
            temp_engine = TfidfFeatureEngine()
            temp_engine.vectorizer = vectorizer_data['vectorizer']
            temp_engine.selector = vectorizer_data['selector']
            temp_engine.use_chi2 = vectorizer_data['use_chi2']
            temp_engine.chi2_k = vectorizer_data['chi2_k']
            self.vectorizer = temp_engine
        else:
            # 旧格式，直接使用
            self.vectorizer = vectorizer_data
            self.vectorizer.use_chi2 = False
            self.vectorizer.selector = None

        self.label_encoder = joblib.load(f"{model_dir}/label_encoder.pkl")
        self.model = joblib.load(f"{model_dir}/model.pkl")

        self.is_fitted = True

        return self

    def get_model_info(self) -> dict:
        """
        获取模型信息
        Get model information

        伪代码 Pseudocode:
        1. 检查模型是否已训练
           Check if model is trained
        2. 获取模型参数
           Get model parameters
        3. 获取特征数量
           Get feature count
        4. 返回模型信息
           Return model info

        返回 Returns:
            dict: 模型信息字典 - Model information dictionary
        """
        # 伪代码实现 - Pseudocode implementation
        if not self.is_fitted:
            return {"status": "not fitted"}

        return {
            "status": "fitted",
            "n_features": self.vectorizer.max_features if self.vectorizer else 0,
            "n_classes": len(self.label_encoder.classes_),
            "multi_class": self.model.multi_class,
            "solver": self.model.solver,
            "max_iter": self.model.max_iter,
            "C": self.model.C
        }


def train_test_split(texts: List[str], labels: List[str],
                   test_size: float = 0.2, random_state: int = 42) -> dict:
    """
    训练-测试集分割
    Train-test split

    伪代码 Pseudocode:
    1. 导入文本列表和标签列表
       Input text list and label list
    2. 划分训练集和测试集
       Split into train and test sets
    3. 返回分割结果
       Return split result

    参数 Parameters:
        texts: 文本列表 - Text list
        labels: 标签列表 - Label list
        test_size: 测试集比例 - Test set ratio
        random_state: 随机种子 - Random seed

    返回 Returns:
        dict: 分割结果 - Split result
    """
    # 伪代码实现 - Pseudocode implementation
    from sklearn.model_selection import train_test_split

    X_train, X_test, y_train, y_test = train_test_split(
        texts, labels,
        test_size=test_size,
        random_state=random_state
    )

    return {
        "train": {"X": X_train, "y": y_train},
        "test": {"X": X_test, "y": y_test},
        "test_size": test_size,
        "random_state": random_state
    }