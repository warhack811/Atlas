import unittest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from Atlas.api import app

client = TestClient(app)

class TestApiFaz7(unittest.TestCase):

    @patch('Atlas.observer.observer.get_notifications', new_callable=AsyncMock)
    def test_get_notifications(self, mock_get):
        mock_get.return_value = [{"id": "n1", "message": "hello"}]
        
        response = client.get("/api/notifications?session_id=user123")
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["notifications"]), 1)
        mock_get.assert_called_once_with("user123")

    @patch('Atlas.memory.neo4j_manager.neo4j_manager.acknowledge_notification', new_callable=AsyncMock)
    def test_ack_notification(self, mock_ack):
        mock_ack.return_value = True
        
        response = client.post("/api/notifications/ack", json={
            "session_id": "user123",
            "notification_id": "n1"
        })
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")

    @patch('Atlas.memory.prospective_store.list_open_tasks', new_callable=AsyncMock)
    def test_get_tasks(self, mock_list):
        mock_list.return_value = [{"id": "t1", "text": "task"}]
        
        response = client.get("/api/tasks?session_id=user123")
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["tasks"]), 1)

    @patch('Atlas.memory.prospective_store.mark_task_done', new_callable=AsyncMock)
    def test_complete_task(self, mock_done):
        mock_done.return_value = True
        
        response = client.post("/api/tasks/done", json={
            "session_id": "user123",
            "task_id": "t1"
        })
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")

if __name__ == "__main__":
    unittest.main()
