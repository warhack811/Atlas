import unittest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from Atlas.api import app

class TestRC2ApiContract(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch('Atlas.memory.neo4j_manager.neo4j_manager.get_user_settings', new_callable=AsyncMock)
    @patch('Atlas.memory.context.build_memory_context_v3', new_callable=AsyncMock)
    @patch('Atlas.memory.prospective_store.list_open_tasks', new_callable=AsyncMock)
    @patch('Atlas.observer.observer.get_notifications', new_callable=AsyncMock)
    def test_memory_get_response_structure(self, mock_notif, mock_tasks, mock_ctx, mock_settings):
        # Mock values
        mock_settings.return_value = {"memory_mode": "STANDARD", "notifications_enabled": False}
        mock_ctx.return_value = "Test context"
        mock_tasks.return_value = []
        mock_notif.return_value = []
        
        response = self.client.get("/api/memory?session_id=s1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["user_id"], "s1")
        self.assertIn("settings", data)

    @patch('Atlas.memory.neo4j_manager.neo4j_manager.set_user_settings', new_callable=AsyncMock)
    def test_policy_post_payload(self, mock_set):
        mock_set.return_value = {"memory_mode": "FULL"}
        
        payload = {
            "session_id": "s1",
            "memory_mode": "FULL",
            "notifications_enabled": True
        }
        response = self.client.post("/api/policy", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

if __name__ == "__main__":
    unittest.main()
