import unittest
from unittest.mock import patch, AsyncMock, MagicMock
from Atlas.memory.context import build_chat_context_v1

class TestRC5Scoring(unittest.IsolatedAsyncioTestCase):
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.get_user_memory_mode', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.get_recent_turns', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.query_graph', new_callable=AsyncMock)
    @patch('Atlas.memory.context.build_memory_context_v3', new_callable=AsyncMock)
    async def test_episode_keyword_weighting(self, mock_v3, mock_query, mock_turns, mock_mode):
        # Setup
        mock_mode.return_value = "STD"
        mock_turns.return_value = []
        mock_v3.return_value = ""
        
        # 2 episodes: biri keyword içeriyor, diğeri içermiyor
        mock_query.return_value = [
            {"summary": "Toplantıda bütçe konuşuldu.", "start": 1, "end": 10, "updated_at": "2026-01-01"},
            {"summary": "Hava çok güzeldi.", "start": 11, "end": 20, "updated_at": "2026-01-02"}
        ]
        
        # User message "bütçe" içeriyor
        context = await build_chat_context_v1("u1", "s1", "Bütçe ne oldu?")
        
        # "bütçe konuşuldu" özetinin üstte (veya var) olması gerekir (skoru arttığı için)
        self.assertIn("bütçe konuşuldu", context)
        # "Hava çok güzeldi" de bütçe dahilindeyse var olabilir ama bütçe öncelikli

if __name__ == "__main__":
    unittest.main()
