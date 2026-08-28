"""
Embedding特征工程模块 - Embedding Feature Engineering Module

基于Sentence-Transformers的文本特征提取
Text feature extraction using Sentence-Transformers

主要功能 Main Functions:
- 初始化Sentence-Transformers模型
- 训练时提取特征
- 推理时提取特征
"""

import numpy as np
from typing import List, Optional


class EmbeddingFeatureEngine:
    """Embedding特征引擎 - Embedding Feature Engine"""

    def __init__(self, model_name: str = 'all-MiniLM-L6-v2', device: str = 'cpu'):
        """
        初始化Embedding特征引擎
        Initialize embedding feature engine

        参数 Parameters:
            model_name: 模型名称 - Model name
            device: 设备 ('cpu' or 'cuda') - Device
        """
        self.model_name = model_name
        self.device = device
        self.model = None
        self.is_fitted = False

    def _load_model(self):
        """延迟加载模型"""
        if self.model is None:
            try:
                from sentence_transformers import SentenceTransformer
                print(f"Loading embedding model: {self.model_name} (device: {self.device})")
                self.model = SentenceTransformer(self.model_name, device=self.device)
                self.is_fitted = True
                print(f"Model loaded successfully. Embedding dimension: {self.model.get_sentence_embedding_dimension()}")
            except ImportError:
                raise ImportError(
                    "sentence-transformers not installed. "
                    "Install with: pip install sentence-transformers"
                )

    def fit_transform(self, texts: List[str], labels: Optional[List[str]] = None) -> np.ndarray:
        """
        加载模型并转换文本为特征矩阵
        Load model and transform texts to feature matrix

        参数 Parameters:
            texts: 文本列表 - Text list
            labels: 标签列表（未使用，保持接口一致） - Label list (unused, for interface consistency)

        返回 Returns:
            np.ndarray: 特征矩阵 - Feature matrix
        """
        # 延迟加载模型
        self._load_model()

        print(f"Extracting embeddings for {len(texts)} texts...")
        embeddings = self.model.encode(texts, show_progress_bar=True)
        print(f"Embeddings shape: {embeddings.shape}")

        return embeddings

    def transform(self, texts: List[str]) -> np.ndarray:
        """
        使用已加载的模型转换文本为特征矩阵
        Transform texts to feature matrix using loaded model

        参数 Parameters:
            texts: 文本列表 - Text list

        返回 Returns:
            np.ndarray: 特征矩阵 - Feature matrix
        """
        if not self.is_fitted:
            raise ValueError("Model not loaded. Call fit_transform first")

        print(f"Extracting embeddings for {len(texts)} texts...")
        embeddings = self.model.encode(texts, show_progress_bar=False)
        return embeddings

    def get_embedding_dim(self) -> int:
        """获取embedding维度"""
        if self.model is not None:
            return self.model.get_sentence_embedding_dimension()
        return 0

    def save_model(self, path: str):
        """
        保存模型信息
        Save model info (embedding models are loaded from HuggingFace)

        参数 Parameters:
            path: 保存路径 - Save path
        """
        import joblib
        model_info = {
            'model_name': self.model_name,
            'device': self.device,
            'embedding_dim': self.get_embedding_dim(),
            'use_embedding': True
        }
        joblib.dump(model_info, path)

    def load_model(self, path: str):
        """
        加载模型信息
        Load model info

        参数 Parameters:
            path: 加载路径 - Load path
        """
        import joblib
        model_info = joblib.load(path)
        self.model_name = model_info.get('model_name', 'all-MiniLM-L6-v2')
        self.device = model_info.get('device', 'cpu')
        # 模型会延迟加载
        print(f"Embedding config loaded: {self.model_name} on {self.device}")