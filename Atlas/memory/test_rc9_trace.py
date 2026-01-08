import unittest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from Atlas.memory.context import build_chat_context_v1
from Atlas.memory.trace import ContextTrace

class TestRC9Trace(unittest.TestCase):
    @patch("Atlas.memory.neo4j_manager.neo4j_manager.get_user_memory_mode")
    @patch("Atlas.memory.neo4j_manager.neo4j_manager.get_recent_turns")
    @patch("Atlas.memory.neo4j_manager.neo4j_manager.query_graph")
    @patch("Atlas.memory.intent.classify_intent_tr")
    @patch("Atlas.config.BYPASS_MEMORY_INJECTION", False)
    def test_trace_auto_generation(self, mock_intent, mock_query, mock_turns, mock_mode):
        mock_mode.side_effect = AsyncMock(return_value="MIXED")
        mock_turns.side_effect = AsyncMock(return_value=[])
        mock_query.side_effect = AsyncMock(return_value=[])
        mock_intent.return_value = "GENERAL"
        
        trace = ContextTrace(request_id="trace_123", user_id="u1", session_id="s1")
        
        async def run_test():
            return await build_chat_context_v1("u1", "s1", "Hava nasıl?", trace=trace)
            
        asyncio.run(run_test())
        
        self.assertEqual(trace.intent, "GENERAL")
        self.assertEqual(trace.memory_mode, "MIXED")
        self.assertIn("build_total_ms", trace.timings_ms)
        self.assertTrue(any("Noise Guard" in r for r in trace.reasons))

    @patch("Atlas.memory.neo4j_manager.neo4j_manager.get_user_memory_mode")
    @patch("Atlas.memory.neo4j_manager.neo4j_manager.get_recent_turns")
    @patch("Atlas.config.BYPASS_MEMORY_INJECTION", True)
    def test_trace_reason_bypass(self, mock_turns, mock_mode):
        mock_mode.side_effect = AsyncMock(return_value="MIXED")
        mock_turns.side_effect = AsyncMock(return_value=[])
        
        trace = ContextTrace(request_id="trace_456", user_id="u1", session_id="s1")
        
        async def run_test():
            return await build_chat_context_v1("u1", "s1", "Test", trace=trace)
            
        asyncio.run(run_test())
        self.assertIn("BYPASS_MEMORY_INJECTION=true", trace.reasons)

if __name__ == "__main__":
    unittest.main()
