import unittest
from unittest.mock import patch, AsyncMock, MagicMock
from Atlas.memory.neo4j_manager import Neo4jManager

class TestNotificationPersistence(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.manager = Neo4jManager()

    @patch('Atlas.memory.neo4j_manager.Neo4jManager.query_graph', new_callable=AsyncMock)
    async def test_create_notification(self, mock_query):
        mock_query.return_value = [{"id": "notif_123"}]
        
        data = {
            "message": "Test message",
            "type": "test_alert",
            "source": "test_suite"
        }
        notif_id = await self.manager.create_notification("user123", data)
        
        self.assertIsNotNone(notif_id)
        # RC-1: Prefix "notif_" removed, using full UUID hex (32 chars)
        self.assertEqual(len(notif_id), 32)
        
        # Verify query call
        args = mock_query.call_args[0]
        self.assertIn("CREATE (n:Notification", args[0])
        self.assertEqual(args[1]["uid"], "user123")
        self.assertEqual(args[1]["message"], "Test message")

    @patch('Atlas.memory.neo4j_manager.Neo4jManager.query_graph', new_callable=AsyncMock)
    async def test_list_notifications(self, mock_query):
        mock_query.return_value = [
            {"id": "n1", "message": "msg1", "read": False},
            {"id": "n2", "message": "msg2", "read": True}
        ]
        
        notifications = await self.manager.list_notifications("user123", limit=5)
        
        self.assertEqual(len(notifications), 2)
        self.assertEqual(notifications[0]["id"], "n1")

    @patch('Atlas.memory.neo4j_manager.Neo4jManager.query_graph', new_callable=AsyncMock)
    async def test_acknowledge_notification(self, mock_query):
        mock_query.return_value = [{"updated": 1}]
        
        success = await self.manager.acknowledge_notification("user123", "n1")
        
        self.assertTrue(success)
        args = mock_query.call_args[0]
        self.assertIn("SET n.read = true", args[0])

if __name__ == "__main__":
    unittest.main()
