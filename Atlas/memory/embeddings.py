"""
ATLAS RC-10 - Embedding Altyapısı
--------------------------------
Metinleri vektör uzayına taşıyan ve anlamsal benzerlik hesaplayan bileşenler.
Testler için deterministik 'HashEmbedder' ve prod için 'sentence-transformers' desteği sunar.
"""

import hashlib
import numpy as np
from typing import List
from Atlas.config import EMBEDDING_SETTINGS

class BaseEmbedder:
    """Embedder'lar için temel arayüz."""
    def embed(self, text: str) -> List[float]:
        raise NotImplementedError

    def dimension(self) -> int:
        return EMBEDDING_SETTINGS["DIMENSION"]

class HashEmbedder(BaseEmbedder):
    """
    Deterministik Hash-tabanlı Embedder (Test & Offline kullanım için).
    Metni hash'leyerek 0-1 arasında değerlerden oluşan sabit boyutlu bir vektör üretir.
    Network çağrısı gerektirmez, tamamen offline çalışır.
    """
    def embed(self, text: str) -> List[float]:
        dim = self.dimension()
        # Metni temizle ve normalize et
        clean_text = str(text).strip().lower()
        
        vector = []
        for i in range(dim):
            # Her boyut için metin + index kombinasyonunu hashle
            seed = f"{clean_text}_{i}"
            h = hashlib.md5(seed.encode()).hexdigest()
            # 0-1 arasına normalize et
            val = int(h, 16) % 10000 / 10000.0
            vector.append(val)
            
        # Vektörü normalize et (L2)
        v_np = np.array(vector)
        norm = np.linalg.norm(v_np)
        if norm > 0:
            v_np = v_np / norm
            
        return v_np.tolist()

class SentenceTransformersEmbedder(BaseEmbedder):
    """
    Sentence-Transformers kütüphanesini kullanan gerçek embedder.
    Prod ortamında yüksek kaliteli anlamsal yakalama sağlar.
    """
    def __init__(self):
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(EMBEDDING_SETTINGS["MODEL_NAME"])
        except ImportError:
            self.model = None
            print("[UYARI] 'sentence-transformers' kütüphanesi bulunamadı. HashEmbedder'a düşülüyor.")

    def embed(self, text: str) -> List[float]:
        if not self.model:
            return HashEmbedder().embed(text)
        
        vector = self.model.encode(text)
        return vector.tolist()

def get_embedder() -> BaseEmbedder:
    """Config'e göre uygun embedder örneğini döner."""
    provider = EMBEDDING_SETTINGS.get("PROVIDER", "hash").lower()
    
    if provider == "sentence-transformers":
        return SentenceTransformersEmbedder()
    
    return HashEmbedder()
