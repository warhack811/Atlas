import unittest
from unittest.mock import patch, AsyncMock
from Atlas.memory.context import build_chat_context_v1

class TestRC3ContextBuilder(unittest.IsolatedAsyncioTestCase):
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.get_recent_turns', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.get_recent_episodes', new_callable=AsyncMock)
    @patch('Atlas.memory.context.build_memory_context_v3', new_callable=AsyncMock)
    async def test_hybrid_context_structure(self, mock_v3, mock_ep, mock_turns):
        mock_turns.return_value = [{"role": "user", "content": "selam", "turn_index": 0}]
        mock_ep.return_value = [{"summary": "Eski özet", "start_turn": 0, "end_turn": 10}]
        mock_v3.return_value = "Kişisel bilgi yok"
        
        context = await build_chat_context_v1("u1", "s1", "yeni mesaj")
        
        self.assertIn("YAKIN GEÇMİŞ", context)
        self.assertIn("OTURUM ÖZETLERİ", context)
        self.assertIn("KAYITLI KİŞİSEL BİLGİLER", context)
        self.assertIn("Kullanıcı: selam", context)
        self.assertIn("Eski özet", context)

if __name__ == "__main__":
    unittest.main()
