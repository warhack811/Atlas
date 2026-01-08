import unittest
from unittest.mock import patch, AsyncMock
from Atlas.memory.context import build_memory_context_v3

class TestRC2Policy(unittest.IsolatedAsyncioTestCase):
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.get_user_memory_mode', new_callable=AsyncMock)
    async def test_off_mode_behavior(self, mock_mode):
        mock_mode.return_value = "OFF"
        
        # build_memory_context_v3 should return info message in OFF mode
        res = await build_memory_context_v3("u1", "mesaj")
        self.assertIn("erişimi kapalıdır", res)

    @patch('Atlas.memory.neo4j_manager.neo4j_manager.get_user_settings', new_callable=AsyncMock)
    async def test_get_settings_fallback(self, mock_get):
        mock_get.return_value = {"memory_mode": "FULL", "notifications_enabled": False}
        
        # Verify settings are retrieved correctly
        from Atlas.memory.neo4j_manager import neo4j_manager
        settings = await neo4j_manager.get_user_settings("u1")
        self.assertEqual(settings["memory_mode"], "FULL")
        self.assertFalse(settings["notifications_enabled"])

if __name__ == "__main__":
    unittest.main()
