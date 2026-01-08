import unittest
from unittest.mock import patch, MagicMock
from Atlas.memory.embeddings import HashEmbedder, get_embedder, SentenceTransformersEmbedder
from Atlas.config import EMBEDDING_SETTINGS

class TestRC10Embeddings(unittest.TestCase):
    def test_hash_embedder_deterministic(self):
        """Aynı metin her zaman aynı vektörü üretmeli."""
        embedder = HashEmbedder()
        v1 = embedder.embed("Merhaba Dünya")
        v2 = embedder.embed("Merhaba Dünya")
        v3 = embedder.embed("Başka bir metin")
        
        self.assertEqual(v1, v2)
        self.assertNotEqual(v1, v3)
        self.assertEqual(len(v1), EMBEDDING_SETTINGS["DIMENSION"])

    def test_hash_embedder_normalization(self):
        """Vektör L2 normalize edilmiş olmalı (norm == 1)."""
        import numpy as np
        embedder = HashEmbedder()
        v = embedder.embed("Test normalizasyonu")
        norm = np.linalg.norm(np.array(v))
        self.assertAlmostEqual(norm, 1.0, places=5)

    def test_similarity_ranking(self):
        """Benzerlik fonksiyonunun mekanik çalışmasını doğrular."""
        from Atlas.memory.context import calculate_cosine_similarity
        embedder = HashEmbedder()
        
        q = embedder.embed("Ankara hava")
        v_similar = embedder.embed("Ankara hava")
        v_distant = embedder.embed("İstanbul trafik")
        
        sim_high = calculate_cosine_similarity(q, v_similar)
        sim_low = calculate_cosine_similarity(q, v_distant)
        
        self.assertAlmostEqual(sim_high, 1.0, places=5)
        self.assertLess(sim_low, 1.0)

    @patch("builtins.__import__")
    def test_fallback_mechanism(self, mock_import):
        """Import fail durumunda Hash'e düşmeli."""
        def side_effect(name, *args, **kwargs):
            if name == "sentence_transformers":
                raise ImportError("Mocked import error")
            return real_import(name, *args, **kwargs)

        real_import = __import__
        mock_import.side_effect = side_effect
        
        # PROVIDER ST olsa bile import hatasıyla Hash'e düşmeli
        with patch.dict(EMBEDDING_SETTINGS, {"PROVIDER": "sentence-transformers"}):
            embedder = SentenceTransformersEmbedder()
            self.assertIsNone(embedder.model)
            v = embedder.embed("Test")
            self.assertEqual(len(v), EMBEDDING_SETTINGS["DIMENSION"])

if __name__ == "__main__":
    unittest.main()
