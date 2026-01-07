import unittest
from unittest.mock import patch, MagicMock
import asyncio
from Atlas.memory.context import build_chat_context_v1

class TestRC8Precision(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.uid = "test_user"
        self.sid = "session_1"

    @patch('Atlas.memory.neo4j_manager.neo4j_manager.get_user_memory_mode')
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.get_recent_turns')
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.query_graph')
    @patch('Atlas.memory.context.build_memory_context_v3')
    async def test_general_intent_filtering(self, mock_v3, mock_query, mock_turns, mock_mode):
        # GENERAL intent (Hava nasıl?) semantic hafızayı kapatmalı
        mock_mode.return_value = "STD"
        mock_turns.return_value = []
        mock_query.return_value = []
        mock_v3.return_value = "### Kullanıcı Profili\n- İSİM: Test" # Normalde bu dönmez ama mock
        
        user_msg = "Hava nasıl bugün?"
        stats = {}
        context = await build_chat_context_v1(self.uid, self.sid, user_msg, stats=stats)
        
        self.assertEqual(stats["intent"], "GENERAL")
        self.assertEqual(stats["layer_usage"]["semantic"], 0)
        self.assertNotIn("Kullanıcı Profili", context)

    @patch('Atlas.memory.neo4j_manager.neo4j_manager.get_user_memory_mode')
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.get_recent_turns')
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.query_graph')
    @patch('Atlas.memory.context.build_memory_context_v3')
    async def test_personal_intent_budget(self, mock_v3, mock_query, mock_turns, mock_mode):
        # PERSONAL intent semantic ağırlıklı olmalı
        mock_mode.return_value = "STD"
        mock_turns.return_value = []
        mock_query.return_value = []
        mock_v3.return_value = "### Kullanıcı Profili\n- İSİM: Test"
        
        user_msg = "Kendim hakkında ne biliyorsun?"
        stats = {}
        await build_chat_context_v1(self.uid, self.sid, user_msg, stats=stats)
        
        self.assertEqual(stats["intent"], "PERSONAL")
        # PERSONAL profile: semantic 0.50 -> 6000 * 0.5 = 3000
        # build_chat_context_v1'de semantic_budget bu değer olmalı
        # (Dolaylı kontrol: layer_usage semantic bütçeyi yansıtır)
        self.assertGreater(stats["layer_usage"]["semantic"], 0)

if __name__ == "__main__":
    unittest.main()
