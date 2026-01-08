import unittest
import asyncio
from unittest.mock import patch, MagicMock
from Atlas.memory.context import build_chat_context_v1
from Atlas.memory.trace import ContextTrace

class TestRC9Trace(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    @patch("Atlas.memory.neo4j_manager.neo4j_manager.get_user_memory_mode")
    @patch("Atlas.memory.neo4j_manager.neo4j_manager.get_recent_turns")
    @patch("Atlas.memory.neo4j_manager.neo4j_manager.get_hard_facts")
    @patch("Atlas.memory.neo4j_manager.neo4j_manager.get_soft_signals")
    @patch("Atlas.memory.neo4j_manager.neo4j_manager.get_relevant_episodes")
    @patch("Atlas.memory.intent.classify_intent_tr")
    @patch("Atlas.config.BYPASS_MEMORY_INJECTION", False)
    def test_trace_auto_generation(self, mock_intent, mock_episodes, mock_soft, mock_hard, mock_turns, mock_mode):
        mock_mode.return_value = asyncio.Future()
        mock_mode.return_value.set_result("MIXED")
        
        mock_turns.return_value = asyncio.Future()
        mock_turns.return_value.set_result([])
        
        mock_hard.return_value = asyncio.Future()
        mock_hard.return_value.set_result([])
        
        mock_soft.return_value = asyncio.Future()
        mock_soft.return_value.set_result([])
        
        mock_episodes.return_value = asyncio.Future()
        mock_episodes.return_value.set_result([])

        mock_intent.return_value = "GENERAL"
        
        stats = {}
        context = self.loop.run_until_complete(build_chat_context_v1("u1", "s1", "Test", stats=stats))
        
        self.assertIn("trace", stats)
        trace_data = stats["trace"]
        self.assertEqual(trace_data["intent"], "GENERAL")
        self.assertEqual(trace_data["memory_mode"], "MIXED")
        self.assertIn("build_total_ms", trace_data["timings_ms"])
        
        # GENERAL intent'te semantic budget 0'dır, reason eklenmiş mi?
        # build_chat_context_v1 semantic budget 0 olsa bile build_memory_context_v3 çağırır.
        # build_memory_context_v3 niyet GENERAL ise reason ekler.
        self.assertTrue(any("intent=GENERAL" in r for r in trace_data["reasons"]))

    @patch("Atlas.memory.neo4j_manager.neo4j_manager.get_user_memory_mode")
    @patch("Atlas.memory.neo4j_manager.neo4j_manager.get_recent_turns")
    @patch("Atlas.config.BYPASS_MEMORY_INJECTION", True)
    def test_trace_reason_bypass(self, mock_turns, mock_mode):
        mock_mode.return_value = asyncio.Future()
        mock_mode.return_value.set_result("MIXED")
        
        mock_turns.return_value = asyncio.Future()
        mock_turns.return_value.set_result([])
        
        stats = {}
        context = self.loop.run_until_complete(build_chat_context_v1("u1", "s1", "Test", stats=stats))
        
        trace_data = stats["trace"]
        self.assertIn("BYPASS_MEMORY_INJECTION=true", trace_data["reasons"])

if __name__ == "__main__":
    unittest.main()
