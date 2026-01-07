import unittest
from unittest.mock import patch, AsyncMock
from Atlas.memory.context import build_memory_context_v3

class TestRC1Policy(unittest.IsolatedAsyncioTestCase):

    @patch('Atlas.memory.neo4j_manager.Neo4jManager.get_user_memory_mode', new_callable=AsyncMock)
    @patch('Atlas.memory.context._retrieve_identity_facts', new_callable=AsyncMock)
    async def test_build_memory_context_v3_off_mode(self, mock_identity, mock_mode):
        # Case: Memory mode is OFF
        mock_mode.return_value = "OFF"
        mock_identity.return_value = []
        
        context = await build_memory_context_v3("u1", "mesaj")
        
        # OFF modunda kişisel bilgi olmamalı
        self.assertIn("Hafıza modu kapalı", context)
        mock_identity.assert_not_called()

    @patch('Atlas.memory.neo4j_manager.Neo4jManager.get_user_memory_mode', new_callable=AsyncMock)
    @patch('Atlas.memory.context._retrieve_identity_facts', new_callable=AsyncMock)
    @patch('Atlas.memory.context._retrieve_hard_facts', new_callable=AsyncMock)
    @patch('Atlas.memory.context._retrieve_soft_signals', new_callable=AsyncMock)
    async def test_build_memory_context_v3_standard_mode(self, mock_soft, mock_hard, mock_identity, mock_mode):
        # Case: Memory mode is STANDARD
        mock_mode.return_value = "STANDARD"
        mock_identity.return_value = [{"predicate": "İSİM", "object": "Ali"}]
        mock_hard.return_value = []
        mock_soft.return_value = []
        
        context = await build_memory_context_v3("u1", "mesaj")
        
        self.assertIn("İSİM: Ali", context)
        mock_identity.assert_called_once()

if __name__ == "__main__":
    unittest.main()
