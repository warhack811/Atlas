"""
Atlas Memory - FAZ 5 Lifecycle Engine Tests
--------------------------------------------
Unit testler: resolve_conflicts() ve lifecycle kuralları

Test Coverage:
- EXCLUSIVE overwrite: YAŞAR_YER İstanbul → Ankara
- EXCLUSIVE same value: İSİM Ahmet → Ahmet (update)
- ADDITIVE accumulate: SEVER Pizza + Sushi
- SUPERSEDED retrieval'e düşmez
- Multi-user: userA supersede edince userB etkilenmez
- Provenance alanları bozulmuyor
"""

import unittest
from unittest.mock import patch, AsyncMock, MagicMock
from Atlas.memory.lifecycle_engine import (
    resolve_conflicts,
    _find_active_relationship,
    supersede_relationship
)


class TestExclusiveOverwrite(unittest.IsolatedAsyncioTestCase):
    """EXCLUSIVE predicate overwrite testleri"""
    
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.query_graph', new_callable=AsyncMock)
    async def test_exclusive_different_value_supersedes_old(self, mock_query):
        """EXCLUSIVE predicate: farklı değer ile eski SUPERSEDED olur"""
        # Mock catalog
        mock_catalog = MagicMock()
        mock_catalog.resolve_predicate = MagicMock(return_value="YASAR_YER")
        mock_catalog.get_type = MagicMock(return_value="EXCLUSIVE")
        
        # Eski değer: İstanbul (ACTIVE)
        mock_query.return_value = [{"object": "İstanbul", "turn_id": "turn_001"}]
        
        # Yeni triplet: Ankara
        triplets = [{
            "subject": "__USER__::user123",
            "predicate": "YAŞAR_YER",
            "object": "Ankara"
        }]
        
        new_triplets, supersede_ops = await resolve_conflicts(
            triplets, "user123", "turn_002", mock_catalog
        )
        
        # Yeni triplet eklenmeli
        self.assertEqual(len(new_triplets), 1)
        self.assertEqual(new_triplets[0]["object"], "Ankara")
        
        # Supersede operation oluşturulmalı
        self.assertEqual(len(supersede_ops), 1)
        self.assertEqual(supersede_ops[0]["old_object"], "İstanbul")
        self.assertEqual(supersede_ops[0]["new_turn_id"], "turn_002")
    
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.query_graph', new_callable=AsyncMock)
    async def test_exclusive_same_value_no_supersede(self, mock_query):
        """EXCLUSIVE predicate: aynı değer ile supersede olmaz (update)"""
        # Mock catalog
        mock_catalog = MagicMock()
        mock_catalog.resolve_predicate = MagicMock(return_value="ISIM")
        mock_catalog.get_type = MagicMock(return_value="EXCLUSIVE")
        
        # Eski değer: Ahmet (ACTIVE)
        mock_query.return_value = [{"object": "Ahmet", "turn_id": "turn_001"}]
        
        # Yeni triplet: Ahmet (aynı)
        triplets = [{
            "subject": "__USER__::user123",
            "predicate": "İSİM",
            "object": "Ahmet"
        }]
        
        new_triplets, supersede_ops = await resolve_conflicts(
            triplets, "user123", "turn_002", mock_catalog
        )
        
        # Yeni triplet eklenmeli (MERGE ile update edilecek)
        self.assertEqual(len(new_triplets), 1)
        
        # Supersede operation OLMAMALI
        self.assertEqual(len(supersede_ops), 0)


class TestAdditiveAccumulate(unittest.IsolatedAsyncioTestCase):
    """ADDITIVE predicate accumulation testleri"""
    
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.fact_exists', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.query_graph', new_callable=AsyncMock)
    async def test_additive_accumulates_multiple_values(self, mock_query, mock_exists):
        """ADDITIVE predicate: birden fazla değer accumulate edilir"""
        # Mock catalog
        mock_catalog = MagicMock()
        mock_catalog.resolve_predicate = MagicMock(return_value="SEVER")
        mock_catalog.get_type = MagicMock(return_value="ADDITIVE")
        
        # Pizza zaten var, Sushi yok
        def fact_exists_side_effect(uid, subj, pred, obj):
            return obj == "Pizza"  # Pizza var, Sushi yok
        
        mock_exists.side_effect = fact_exists_side_effect
        
        # Yeni triplets: Pizza (recurrence) + Sushi (new)
        triplets = [
            {"subject": "__USER__::user123", "predicate": "SEVER", "object": "Pizza"},
            {"subject": "__USER__::user123", "predicate": "SEVER", "object": "Sushi"}
        ]
        
        new_triplets, supersede_ops = await resolve_conflicts(
            triplets, "user123", "turn_002", mock_catalog
        )
        
        # İkisi de eklenmeli (MERGE ile Pizza update, Sushi CREATE)
        self.assertEqual(len(new_triplets), 2)
        
        # Supersede OLMAMALI (ADDITIVE)
        self.assertEqual(len(supersede_ops), 0)


class TestSupersededNotInRetrieval(unittest.TestCase):
    """SUPERSEDED relationship'lerin retrieval'e düşmediği testi"""
    
    def test_context_uses_active_filter(self):
        """Context retrieval SUPERSEDED'leri filtreliyor mu?"""
        # Bu test context.py'deki query'leri kontrol eder
        from Atlas.memory.context import _retrieve_identity_facts
        
        # Query'de status filter olmalı
        import inspect
        source = inspect.getsource(_retrieve_identity_facts)
        
        self.assertIn("status IS NULL OR r.status = 'ACTIVE'", source)
        self.assertNotIn("SUPERSEDED", source.replace("status IS NULL OR r.status = 'ACTIVE'", ""))


class TestMultiUserIsolation(unittest.IsolatedAsyncioTestCase):
    """Multi-user izolasyon testleri"""
    
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.query_graph', new_callable=AsyncMock)
    async def test_user_a_supersede_does_not_affect_user_b(self, mock_query):
        """UserA supersede edince userB etkilenmez"""
        # Mock catalog
        mock_catalog = MagicMock()
        mock_catalog.resolve_predicate = MagicMock(return_value="YASAR_YER")
        mock_catalog.get_type = MagicMock(return_value="EXCLUSIVE")
        
        # UserA için İstanbul → Ankara
        mock_query.return_value = [{"object": "İstanbul", "turn_id": "turnA_001"}]
        
        triplets = [{
            "subject": "__USER__::userA",
            "predicate": "YAŞAR_YER",
            "object": "Ankara"
        }]
        
        new_triplets, supersede_ops = await resolve_conflicts(
            triplets, "userA", "turnA_002", mock_catalog
        )
        
        # Supersede operation userA için
        self.assertEqual(supersede_ops[0]["user_id"], "userA")
        
        # Query uid ile filtrelenmiş mi?
        call_args = mock_query.call_args
        self.assertIn("uid", call_args[0][1])
        self.assertEqual(call_args[0][1]["uid"], "userA")


class TestProvenanceIntegrity(unittest.IsolatedAsyncioTestCase):
    """Provenance alanlarının bozulmadığı testleri"""
    
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.query_graph', new_callable=AsyncMock)
    async def test_supersede_sets_correct_fields(self, mock_query):
        """Supersede operation doğru provenance alanlarını set eder"""
        mock_query.return_value = [{"superseded_count": 1}]
        
        await supersede_relationship(
            "user123",
            "__USER__::user123",
            "YAŞAR_YER",
            "İstanbul",
            "turn_002"
        )
        
        # Query parametreleri doğru mu
        call_args = mock_query.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        
        # Status = SUPERSEDED
        self.assertIn("r.status = 'SUPERSEDED'", query)
        
        # superseded_by_turn_id set ediliyor
        self.assertIn("r.superseded_by_turn_id = $new_turn_id", query)
        self.assertEqual(params["new_turn_id"], "turn_002")
        
        # superseded_at set ediliyor
        self.assertIn("r.superseded_at = datetime()", query)
    
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.query_graph', new_callable=AsyncMock)
    async def test_resolve_preserves_source_turn_id(self, mock_query):
        """resolve_conflicts source_turn_id'yi triplet'lerde koruyor"""
        mock_catalog = MagicMock()
        mock_catalog.resolve_predicate = MagicMock(return_value="SEVER")
        mock_catalog.get_type = MagicMock(return_value="ADDITIVE")
        
        mock_query.return_value = []
        
        # source_turn_id içeren triplet
        triplets = [{
            "subject": "__USER__::user123",
            "predicate": "SEVER",
            "object": "Pizza",
            "source_turn_id_first": "turn_005",
            "schema_version": "2"
        }]
        
        new_triplets, _ = await resolve_conflicts(
            triplets, "user123", "turn_005", mock_catalog
        )
        
        # Provenance alanları korunmuş mu
        self.assertEqual(new_triplets[0]["source_turn_id_first"], "turn_005")
        self.assertEqual(new_triplets[0]["schema_version"], "2")


if __name__ == "__main__":
    unittest.main()
