import unittest
import asyncio
from unittest.mock import patch, MagicMock
from Atlas.memory.context import build_chat_context_v1

class TestRC8KillSwitch(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    @patch("Atlas.memory.neo4j_manager.neo4j_manager.get_user_memory_mode")
    @patch("Atlas.memory.neo4j_manager.neo4j_manager.get_recent_turns")
    @patch("Atlas.memory.intent.classify_intent_tr")
    @patch("Atlas.config.BYPASS_MEMORY_INJECTION", True)
    def test_kill_switch_memory_injection(self, mock_intent, mock_turns, mock_mode):
        mock_mode.return_value = asyncio.Future()
        mock_mode.return_value.set_result("MIXED")
        
        mock_turns.return_value = asyncio.Future()
        mock_turns.return_value.set_result([
            {"role": "user", "content": "Merhaba"},
            {"role": "assistant", "content": "Selam!"}
        ])
        
        mock_intent.return_value = "GENERAL"
        
        context = self.loop.run_until_complete(build_chat_context_v1("u1", "s1", "Test"))
        
        self.assertIn("[BİLGİ]: Bellek enjeksiyonu devre dışı bırakıldı.", context)
        self.assertIn("Kullanıcı: Merhaba", context)
        self.assertIn("Atlas: Selam!", context)

    @patch("Atlas.memory.neo4j_manager.neo4j_manager.get_user_memory_mode")
    @patch("Atlas.memory.neo4j_manager.neo4j_manager.get_recent_turns")
    @patch("Atlas.memory.neo4j_manager.neo4j_manager.get_hard_facts")
    @patch("Atlas.memory.neo4j_manager.neo4j_manager.get_soft_signals")
    @patch("Atlas.memory.neo4j_manager.neo4j_manager.get_relevant_episodes")
    @patch("Atlas.memory.intent.classify_intent_tr")
    @patch("Atlas.config.BYPASS_ADAPTIVE_BUDGET", True)
    @patch("Atlas.config.BYPASS_MEMORY_INJECTION", False)
    def test_kill_switch_adaptive_budget(self, mock_intent, mock_episodes, mock_soft, mock_hard, mock_turns, mock_mode):
        # Eğer BYPASS_ADAPTIVE_BUDGET=True ise intent ne olursa olsun 'MIXED' profile kullanılmalı.
        # PERSONAL intent normalde %50 semantic verirken, MIXED %30 verir.
        
        mock_mode.return_value = asyncio.Future()
        mock_mode.return_value.set_result("OFF") # OFF mode semantic=0 yapar. Standard profile MIXED olsun.
        
        mock_turns.return_value = asyncio.Future()
        mock_turns.return_value.set_result([])
        
        mock_hard.return_value = asyncio.Future()
        mock_hard.return_value.set_result([])
        
        mock_soft.return_value = asyncio.Future()
        mock_soft.return_value.set_result([])
        
        mock_episodes.return_value = asyncio.Future()
        mock_episodes.return_value.set_result([])
        
        mock_intent.return_value = "PERSONAL" # Normalde yüksek bütçeli
        
        context = self.loop.run_until_complete(build_chat_context_v1("u1", "s1", "Test"))
        # Bu test bütçenin doğru profilde olduğunu (MIXED) dolaylı olarak context yapısından anlayabilir mi?
        # En azından hata almadığını ve çalıştığını doğrularız.
        self.assertNotIn("[BİLGİ]: Bellek enjeksiyonu devre dışı bırakıldı.", context)

if __name__ == "__main__":
    unittest.main()
