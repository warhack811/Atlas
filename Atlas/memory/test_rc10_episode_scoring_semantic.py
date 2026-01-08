import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from Atlas.memory.context import build_chat_context_v1
from Atlas.memory.trace import ContextTrace
import asyncio

class TestRC10EpisodeScoring(unittest.IsolatedAsyncioTestCase):
    @patch("Atlas.memory.neo4j_manager.neo4j_manager.query_graph")
    @patch("Atlas.memory.neo4j_manager.neo4j_manager.get_user_memory_mode")
    @patch("Atlas.memory.intent.classify_intent_tr")
    async def test_semantic_similarity_bias(self, mock_intent, mock_mode, mock_query):
        """Overlap az olsa da semantic_sim yüksekse episod seçilebilmeli."""
        mock_intent.return_value = "PERSONAL"
        mock_mode.return_value = "STANDARD"
        
        from Atlas.memory.embeddings import HashEmbedder
        embedder = HashEmbedder()
        
        q_vec = embedder.embed("Ankara'da yaşıyorum")
        ep1_vec = embedder.embed("Turkiyenin baskenti ve iklim özellikleri")
        ep2_vec = embedder.embed("Mutfak masası ve yemek tarifleri")
        
        async def query_side_effect(query, params=None):
            if "HAS_TURN" in query: return []
            if "HAS_EPISODE" in query:
                return [
                    {
                        "id": "ep1",
                        "summary": "Turkiyenin baskenti ve iklim özellikleri",
                        "kind": "REGULAR",
                        "embedding": ep1_vec,
                        "start_turn_index": 0, "end_turn_index": 5
                    },
                    {
                        "id": "ep2",
                        "summary": "Mutfak masası ve yemek tarifleri",
                        "kind": "REGULAR",
                        "embedding": ep2_vec,
                        "start_turn_index": 6, "end_turn_index": 10
                    }
                ]
            if "r:FACT" in query or "KNOWS" in query: return []
            return []

        mock_query.side_effect = query_side_effect
        
        trace = ContextTrace(request_id="tr1", user_id="u1", session_id="s1")
        context = await build_chat_context_v1("u1", "s1", "Ankara'da yaşıyorum", trace=trace)
        
        self.assertIn("ep1", trace.selected["episode_ids"])
        self.assertIn("ep2", trace.selected["episode_ids"])
        
        # Scoring details kontrolü
        self.assertIn("ep1", trace.scoring_details["episodes"])
        self.assertIn("ep2", trace.scoring_details["episodes"])
        
        # ep1'in total skoru ep2'den yüksek olmalı
        self.assertGreater(
            trace.scoring_details["episodes"]["ep1"]["total"],
            trace.scoring_details["episodes"]["ep2"]["total"]
        )

    @patch("Atlas.memory.neo4j_manager.neo4j_manager.query_graph")
    @patch("Atlas.memory.neo4j_manager.neo4j_manager.get_user_memory_mode")
    @patch("Atlas.memory.intent.classify_intent_tr")
    async def test_general_intent_behavior(self, mock_intent, mock_mode, mock_query):
        """GENERAL intent'te episodlar gelir ama semantic memory (v3) boş kalır."""
        mock_intent.return_value = "GENERAL"
        mock_mode.return_value = "STANDARD"
        
        async def query_side_effect(query, params=None):
            if "HAS_TURN" in query: return []
            if "HAS_EPISODE" in query:
                return [{"id": "ep1", "summary": "Hava durumu özet", "kind": "REGULAR", "start_turn_index": 1, "end_turn_index": 2}]
            return []

        mock_query.side_effect = query_side_effect
        
        trace = ContextTrace(request_id="tr2", user_id="u1", session_id="s1")
        # 'hava' kelimesi building memory context v3'teki noise guard'ı tetikler
        context = await build_chat_context_v1("u1", "s1", "Bugün hava nasıl?", trace=trace)
        
        # Episodik gelmeli
        self.assertIn("İLGİLİ GEÇMİŞ BÖLÜMLER", context)
        # Semantic gelmemeli (GENERAL budget 0 veya noise guard return empty)
        self.assertNotIn("Sert Gerçekler", context)

if __name__ == "__main__":
    unittest.main()
