
import unittest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException
from Atlas.memory.extractor import sanitize_triplets
from Atlas.memory.lifecycle_engine import resolve_conflicts
from Atlas.memory.context import build_chat_context_v1
from Atlas.memory.trace import ContextTrace
from Atlas.config import Config, MEMORY_CONFIDENCE_SETTINGS

class TestRC11Feedback(unittest.IsolatedAsyncioTestCase):
    
    def setUp(self):
        self.user_id = "test_user_rc11"
        self.session_id = "test_sess_rc11"

    @patch("Atlas.memory.predicate_catalog.get_catalog")
    def test_rc11_soft_signal_not_hard_fact(self, mock_get_catalog):
        """Düşük confidence'lı veriler soft_signal category'sine düşmeli."""
        mock_catalog = MagicMock()
        mock_catalog.resolve_predicate.return_value = "YAŞAR_YER"
        mock_catalog.get_enabled.return_value = True
        mock_catalog.get_canonical.return_value = "YAŞAR_YER"
        mock_catalog.get_durability.return_value = "PERSISTENT"
        mock_catalog.get_graph_category.return_value = "personal"
        mock_get_catalog.return_value = mock_catalog

        # Case 1: High confidence (Hard Fact)
        triplets_high = [{"subject": "Ali", "predicate": "YAŞAR_YER", "object": "Ankara", "confidence": 1.0}]
        cleaned_high = sanitize_triplets(triplets_high, self.user_id, "Ali Ankara'da yaşıyor.")
        self.assertEqual(cleaned_high[0]["category"], "personal")

        # Case 2: Low confidence (Soft Signal)
        triplets_low = [{"subject": "Ali", "predicate": "YAŞAR_YER", "object": "İstanbul", "confidence": 0.5}]
        cleaned_low = sanitize_triplets(triplets_low, self.user_id, "Ali belki İstanbul'da yaşıyordur.")
        self.assertEqual(cleaned_low[0]["category"], "soft_signal")

    @patch("Atlas.memory.neo4j_manager.Neo4jManager.query_graph", new_callable=AsyncMock)
    async def test_rc11_correction_replace_updates_metadata(self, mock_query):
        """Manual düzeltme attribution: USER_CORRECTION ve confidence: 1.0 olmalı."""
        from Atlas.memory.neo4j_manager import neo4j_manager
        mock_query.return_value = [{"count": 1}]
        
        count = await neo4j_manager.correct_memory(
            self.user_id, "fact", "YAŞAR_YER", "İzmir", "replace", "Yanlış biliyorsun"
        )
        self.assertGreater(count, 0)

    @patch("Atlas.memory.neo4j_manager.Neo4jManager.query_graph", new_callable=AsyncMock)
    async def test_rc11_correction_scope_subject(self, mock_query):
        """Düzeltme sadece belirtilen subject_id için geçerli olmalı."""
        from Atlas.memory.neo4j_manager import neo4j_manager
        mock_query.return_value = [{"count": 1}]
        
        await neo4j_manager.correct_memory(
            self.user_id, "fact", "YAŞAR_YER", "Bursa", "replace", "Mert Bursa'da", subject_id="Mert"
        )
        
        last_query = mock_query.call_args_list[0][0][0]
        self.assertIn("s:Entity {name: $sid}", last_query)
        self.assertEqual(mock_query.call_args_list[0][0][1]["sid"], "Mert")

    @patch("Atlas.memory.neo4j_manager.Neo4jManager.get_user_memory_mode", new_callable=AsyncMock)
    @patch("Atlas.memory.predicate_catalog.get_catalog")
    async def test_rc11_correction_off_mode_blockade(self, mock_get_catalog, mock_mode):
        """Hafıza kapalıyken (OFF) düzeltme girişimi 403 vermeli."""
        from Atlas.api import correct_memory, MemoryCorrectionRequest
        mock_mode.return_value = "OFF"
        
        req = MemoryCorrectionRequest(
            session_id=self.session_id,
            user_id=self.user_id,
            target_type="fact",
            predicate="YAŞAR_YER",
            mode="retract"
        )
        
        with self.assertRaises(HTTPException) as cm:
            await correct_memory(req)
        self.assertEqual(cm.exception.status_code, 403)

    @patch("Atlas.memory.neo4j_manager.Neo4jManager.query_graph", new_callable=AsyncMock)
    @patch("Atlas.memory.predicate_catalog.get_catalog")
    async def test_rc11_conflict_high_confidence_only(self, mock_get_catalog, mock_query):
        """Conflict sadece her iki taraf da yüksek confidence ise tetiklenmeli."""
        mock_catalog = MagicMock()
        mock_catalog.resolve_predicate.return_value = "YAŞAR_YER"
        mock_catalog.get_type.return_value = "EXCLUSIVE"
        mock_get_catalog.return_value = mock_catalog
        
        mock_query.side_effect = [
            [{"object": "Ankara", "confidence": 0.5}], # _find_active_relationship
            [{"count": 1}] # store_triplets update logic
        ]
        
        triplets = [{"subject": "Ali", "predicate": "YAŞAR_YER", "object": "İstanbul", "confidence": 0.9}]
        new_triplets, ops = await resolve_conflicts(triplets, self.user_id, "t1", mock_catalog)
        
        self.assertEqual(ops[0]["type"], "SUPERSEDE")
        self.assertNotIn("status", new_triplets[0])

    @patch("Atlas.memory.neo4j_manager.Neo4jManager.query_graph", new_callable=AsyncMock)
    async def test_rc11_conflict_to_open_question_mapping(self, mock_query):
        """CONFLICTED kayıtlar context build sırasında Open Question'a dönüşmeli."""
        async def query_side_effect(query, params=None):
            # Debug için query tipini yazdıralım (stdout'a gider)
            q_clean = query[:120].replace('\n', ' ')
            print(f"MOCK_QUERY: {q_clean}")
            
            if "User {id: $uid}" in query:
                return [{"u": {"memory_mode": "STANDARD"}}]
            if "HAS_TURN" in query:
                return []
            if "predicate IN ['İSİM'" in query:
                return [{"predicate": "İSİM", "object": "TestUser"}]
            if "EXCLUSIVE" in query or "MATCH (s:Entity)-[r:FACT" in query:
                if "status: 'CONFLICTED'" in query:
                    return [{"predicate": "YAŞAR_YER", "value": "Ankara"}, {"predicate": "YAŞAR_YER", "value": "İstanbul"}]
                return [] # Hard facts / Soft signals empty
            if "HAS_EPISODE" in query:
                return []
            return []

        mock_query.side_effect = query_side_effect
        
        trace = ContextTrace(request_id="t1", user_id="u1", session_id="s1")
        # 'Hangi' is a trigger for PERSONAL intent
        context = await build_chat_context_v1("Hangi takımı tutuyorum?", self.user_id, self.session_id, trace=trace)
        
        self.assertIn("Hangi bilgi", context)
        self.assertEqual(trace.metrics["conflicts_detected_count"], 1)

    def test_rc11_trace_counts(self):
        """Trace objesi yeni RC-11 metriklerini tutmalı."""
        trace = ContextTrace(request_id="t1", user_id="u1", session_id="s1")
        self.assertIn("conflicts_detected_count", trace.metrics)
        self.assertIn("writes_skipped", trace.filtered_counts)
        self.assertIn("corrections_applied_count", trace.metrics)

if __name__ == "__main__":
    unittest.main()
