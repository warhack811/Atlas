"""
Atlas Memory - FAZ 6 Context Packaging V3 Tests
------------------------------------------------
Unit testler: build_memory_context_v3() fonksiyonu ve yardımcıları

Test Coverage:
- OFF mode → kişisel hafıza kapalı
- STANDARD mode → identity, hard, soft ayrımı
- EXCLUSIVE → hard facts
- ADDITIVE → soft signals
- Status filter → SUPERSEDED görünmez
- User izolasyonu (multi-user)
- Truncation (Hard:20, Soft:20, Open:10)
- Boş graph durumda format bozulmuyor
- Open Questions minimal
- Anchor subject doğru kullanılıyor
"""

import unittest
from unittest.mock import patch, AsyncMock, MagicMock
from Atlas.memory.context import (
    build_memory_context_v3,
    _build_off_mode_context,
    _build_minimal_context,
    _retrieve_identity_facts,
    _retrieve_hard_facts,
    _retrieve_soft_signals,
    _generate_open_questions,
    _format_context_v3
)


class TestBuildMemoryContextV3(unittest.IsolatedAsyncioTestCase):
    """build_memory_context_v3() ana fonksiyon testleri"""
    
    async def test_off_mode_returns_off_context(self):
        """MemoryPolicy.OFF ise kişisel hafıza kapalı context döner"""
        # Mock policy OFF
        mock_policy = MagicMock()
        mock_policy.mode = "OFF"
        
        result = await build_memory_context_v3("user123", "test message", policy=mock_policy)
        
        self.assertIn("Hafıza modu kapalı", result)
        self.assertIn("### Kullanıcı Profili", result)
        self.assertIn("### Sert Gerçekler", result)
        self.assertIn("### Yumuşak Sinyaller", result)
        self.assertIn("### Açık Sorular", result)
    
    @patch('Atlas.memory.context.get_catalog')
    async def test_no_catalog_returns_minimal_context(self, mock_get_catalog):
        """Catalog yüklenemediyse minimal context döner"""
        mock_get_catalog.return_value = None
        
        # Mock policy STANDARD
        mock_policy = MagicMock()
        mock_policy.mode = "STANDARD"
        
        result = await build_memory_context_v3("user123", "test message", policy=mock_policy)
        
        self.assertIn("Bellek sistemi geçici olarak kullanılamıyor", result)
    
    @patch('Atlas.memory.context._retrieve_identity_facts', new_callable=AsyncMock)
    @patch('Atlas.memory.context._retrieve_hard_facts', new_callable=AsyncMock)
    @patch('Atlas.memory.context._retrieve_soft_signals', new_callable=AsyncMock)
    @patch('Atlas.memory.context.get_catalog')
    @patch('Atlas.memory.context.load_policy_for_user')
    async def test_standard_mode_retrieves_all_sections(
        self, mock_load_policy, mock_get_catalog,
        mock_soft, mock_hard, mock_identity
    ):
        """STANDARD mode: identity, hard, soft retrieval çalışır"""
        # Mock policy
        mock_policy = MagicMock()
        mock_policy.mode = "STANDARD"
        mock_load_policy.return_value = mock_policy
        
        # Mock catalog
        mock_catalog = MagicMock()
        mock_catalog.by_key = {}
        mock_get_catalog.return_value = mock_catalog
        
        # Mock retrieval fonksiyonları
        mock_identity.return_value = [{"predicate": "İSİM", "object": "Ali"}]
        mock_hard.return_value = [{"subject": "Ali", "predicate": "EŞİ", "object": "Ayşe"}]
        mock_soft.return_value = [{"subject": "Ali", "predicate": "SEVER", "object": "Pizza"}]
        
        result = await build_memory_context_v3("user123", "test message")
        
        # Tüm bölümler mevcut mu
        self.assertIn("### Kullanıcı Profili", result)
        self.assertIn("İSİM: Ali", result)
        self.assertIn("### Sert Gerçekler", result)
        self.assertIn("Ali - EŞİ - Ayşe", result)
        self.assertIn("### Yumuşak Sinyaller", result)
        self.assertIn("Ali - SEVER - Pizza", result)
        self.assertIn("### Açık Sorular", result)
    
    async def test_off_mode_context_format(self):
        """OFF mode context formatı doğru"""
        result = _build_off_mode_context()
        
        self.assertIn("### Kullanıcı Profili", result)
        self.assertIn("(Hafıza modu kapalı - kişisel bilgi yok)", result)
        self.assertIn("### Sert Gerçekler (Hard Facts)", result)
        self.assertIn("(Hafıza modu kapalı)", result)
    
    async def test_minimal_context_format(self):
        """Minimal context formatı doğru"""
        result = _build_minimal_context()
        
        self.assertIn("### Kullanıcı Profili", result)
        self.assertIn("(Bellek sistemi geçici olarak kullanılamıyor)", result)


class TestRetrievalFunctions(unittest.IsolatedAsyncioTestCase):
    """Retrieval yardımcı fonksiyon testleri"""
    
    @patch('Atlas.memory.context.neo4j_manager.neo4j_manager.query_graph', new_callable=AsyncMock)
    async def test_retrieve_identity_facts_active_only(self, mock_query):
        """Identity facts sadece ACTIVE olanları döner"""
        mock_query.return_value = [
            {"predicate": "İSİM", "object": "Ali", "updated_at": "2024-01-01"},
            {"predicate": "YAŞI", "object": "25", "updated_at": "2024-01-02"}
        ]
        
        result = await _retrieve_identity_facts("user123", "__USER__::user123")
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["predicate"], "İSİM")
        
        # Query parametreleri doğru mu
        call_args = mock_query.call_args
        self.assertIn("status IS NULL OR r.status = 'ACTIVE'", call_args[0][0])
        self.assertEqual(call_args[0][1]["anchor"], "__USER__::user123")
    
    @patch('Atlas.memory.context.neo4j_manager.neo4j_manager.query_graph', new_callable=AsyncMock)
    async def test_retrieve_hard_facts_exclusive_only(self, mock_query):
        """Hard facts sadece EXCLUSIVE predicates"""
        mock_catalog = MagicMock()
        mock_catalog.by_key = {
            "ESI": {"type": "EXCLUSIVE", "canonical": "EŞİ", "enabled": True},
            "SEVER": {"type": "ADDITIVE", "canonical": "SEVER", "enabled": True},
            "ISIM": {"type": "EXCLUSIVE", "canonical": "İSİM", "enabled": True}
        }
        
        mock_query.return_value = [
            {"subject": "Ali", "predicate": "EŞİ", "object": "Ayşe", "updated_at": "2024-01-01"}
        ]
        
        result = await _retrieve_hard_facts("user123", "__USER__::user123", mock_catalog)
        
        # Sadece EŞİ döner (İSİM identity'de olduğu için hariç)
        self.assertEqual(len(result), 1)
        
        # Query'de EXCLUSIVE predicates var mı
        call_args = mock_query.call_args
        predicates = call_args[0][1]["predicates"]
        self.assertIn("EŞİ", predicates)
        self.assertNotIn("SEVER", predicates)  # ADDITIVE olduğu için yok
        self.assertNotIn("İSİM", predicates)  # Identity olduğu için hariç
    
    @patch('Atlas.memory.context.neo4j_manager.neo4j_manager.query_graph', new_callable=AsyncMock)
    async def test_retrieve_soft_signals_additive_temporal(self, mock_query):
        """Soft signals sadece ADDITIVE/TEMPORAL predicates"""
        mock_catalog = MagicMock()
        mock_catalog.by_key = {
            "SEVER": {"type": "ADDITIVE", "canonical": "SEVER", "enabled": True},
            "HISSEDIYOR": {"type": "TEMPORAL", "canonical": "HİSSEDİYOR", "enabled": True},
            "ESI": {"type": "EXCLUSIVE", "canonical": "EŞİ", "enabled": True}
        }
        
        mock_query.return_value = [
            {"subject": "Ali", "predicate": "SEVER", "object": "Pizza", "updated_at": "2024-01-01"},
            {"subject": "Ali", "predicate": "HİSSEDİYOR", "object": "Mutlu", "updated_at": "2024-01-02"}
        ]
        
        result = await _retrieve_soft_signals("user123", mock_catalog)
        
        self.assertEqual(len(result), 2)
        
        # Query'de ADDITIVE/TEMPORAL predicates var mı
        call_args = mock_query.call_args
        predicates = call_args[0][1]["predicates"]
        self.assertIn("SEVER", predicates)
        self.assertIn("HİSSEDİYOR", predicates)
        self.assertNotIn("EŞİ", predicates)  # EXCLUSIVE olduğu için yok


class TestStatusFiltering(unittest.IsolatedAsyncioTestCase):
    """SUPERSEDED/RETRACTED filtering testleri"""
    
    @patch('Atlas.memory.context.neo4j_manager.neo4j_manager.query_graph', new_callable=AsyncMock)
    async def test_superseded_not_in_results(self, mock_query):
        """SUPERSEDED relationship'ler retrieval'e düşmez"""
        # Query'de status filter olduğunu doğrula
        mock_query.return_value = []
        
        await _retrieve_identity_facts("user123", "__USER__::user123")
        
        call_args = mock_query.call_args
        query = call_args[0][0]
        self.assertIn("status IS NULL OR r.status = 'ACTIVE'", query)
        self.assertNotIn("SUPERSEDED", query)


class TestTruncation(unittest.TestCase):
    """Truncation logic testleri"""
    
    def test_identity_truncation_max_10(self):
        """Identity facts max 10 satır"""
        identity_facts = [{"predicate": f"PRED{i}", "object": f"VAL{i}"} for i in range(20)]
        
        result = _format_context_v3(identity_facts, [], [], [])
        
        # Profilde max 10 satır olmalı (header hariç)
        lines = [l for l in result.split("\n") if l.startswith("- PRED")]
        self.assertEqual(len(lines), 10)  # Tam 10 olmalı (truncation sonrası)
    
    def test_hard_facts_truncation_max_20(self):
        """Hard facts max 20 satır"""
        hard_facts = [{"subject": "S", "predicate": f"P{i}", "object": "O"} for i in range(30)]
        
        result = _format_context_v3([], hard_facts, [], [])
        
        # Hard facts max 20 satır (header hariç)
        lines = [l for l in result.split("\n") if l.startswith("- S - P")]
        self.assertEqual(len(lines), 20)  # Tam 20 olmalı
    
    def test_soft_signals_truncation_max_20(self):
        """Soft signals max 20 satır"""
        soft_signals = [{"subject": "S", "predicate": f"P{i}", "object": "O"} for i in range(30)]
        
        result = _format_context_v3([], [], soft_signals, [])
        
        # Soft signals max 20 satır (header hariç)
        lines = [l for l in result.split("\n") if l.startswith("- S - P")]
        self.assertEqual(len(lines), 20)  # Tam 20 olmalı
    
    def test_open_questions_truncation_max_10(self):
        """Open questions max 10 satır"""
        questions = [f"Soru {i}" for i in range(20)]
        
        result = _format_context_v3([], [], [], questions)
        
        # Open questions max 10 satır (header hariç)
        lines = [l for l in result.split("\n") if l.startswith("- Soru")]
        self.assertEqual(len(lines), 10)  # Tam 10 olmalı


class TestOpenQuestions(unittest.TestCase):
    """Open Questions generation testleri"""
    
    def test_missing_essential_identity_generates_questions(self):
        """Eksik essential identity predicates soru üretir"""
        identity_facts = [{"predicate": "İSİM", "object": "Ali"}]
        hard_facts = []
        
        questions = _generate_open_questions(identity_facts, hard_facts, None)
        
        # YAŞI, MESLEĞİ, YAŞAR_YER eksik olmalı
        self.assertIn("yaşı bilinmiyor", " ".join(questions).lower())
        self.assertIn("mesleği bilinmiyor", " ".join(questions).lower())
        self.assertIn("yaşadığı yer bilinmiyor", " ".join(questions).lower())
    
    def test_all_identity_present_no_questions(self):
        """Tüm essential identity varsa soru üretilmez"""
        identity_facts = [
            {"predicate": "İSİM", "object": "Ali"},
            {"predicate": "YAŞI", "object": "25"},
            {"predicate": "MESLEĞİ", "object": "Engineer"},
            {"predicate": "YAŞAR_YER", "object": "İstanbul"}
        ]
        
        questions = _generate_open_questions(identity_facts, [], None)
        
        self.assertEqual(len(questions), 0)


class TestEmptyGraph(unittest.TestCase):
    """Boş graph durumda format testleri"""
    
    def test_empty_graph_format_not_broken(self):
        """Boş graph durumda format bozulmuyor"""
        result = _format_context_v3([], [], [], [])
        
        # Tüm bölümler mevcut
        self.assertIn("### Kullanıcı Profili", result)
        self.assertIn("(Henüz kullanıcı profili bilgisi yok)", result)
        self.assertIn("### Sert Gerçekler", result)
        self.assertIn("(Henüz sert gerçek bilgisi yok)", result)
        self.assertIn("### Yumuşak Sinyaller", result)
        self.assertIn("(Henüz yumuşak sinyal bilgisi yok)", result)
        self.assertIn("### Açık Sorular", result)
        self.assertIn("(Şu an açık soru yok)", result)


class TestAnchorUsage(unittest.IsolatedAsyncioTestCase):
    """Anchor subject kullanımı testleri"""
    
    @patch('Atlas.memory.context.neo4j_manager.neo4j_manager.query_graph', new_callable=AsyncMock)
    @patch('Atlas.memory.context.get_user_anchor')
    async def test_anchor_subject_used_correctly(self, mock_get_anchor, mock_query):
        """Anchor subject doğru kullanılıyor"""
        mock_get_anchor.return_value = "__USER__::user123"
        mock_query.return_value = []
        
        await _retrieve_identity_facts("user123", "__USER__::user123")
        
        # Query parametrelerinde anchor kullanılmış mı
        call_args = mock_query.call_args
        self.assertEqual(call_args[0][1]["anchor"], "__USER__::user123")
        self.assertIn("name: $anchor", call_args[0][0])


if __name__ == "__main__":
    unittest.main()
