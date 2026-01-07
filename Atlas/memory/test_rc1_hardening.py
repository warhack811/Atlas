import unittest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime
from Atlas.memory.neo4j_manager import Neo4jManager
from Atlas.memory.due_scanner import scan_due_tasks

class TestRC1Hardening(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.manager = Neo4jManager()

    @patch('Atlas.memory.neo4j_manager.Neo4jManager.query_graph', new_callable=AsyncMock)
    async def test_get_notification_settings_coalesce(self, mock_query):
        # Case: max_daily is None in DB
        mock_query.return_value = [{
            "enabled": True,
            "mode": "STANDARD",
            "quiet_start": None,
            "quiet_end": None,
            "max_daily": None
        }]
        
        settings = await self.manager.get_notification_settings("u1")
        self.assertEqual(settings["max_daily"], 5)

    @patch('Atlas.memory.neo4j_manager.Neo4jManager.query_graph', new_callable=AsyncMock)
    async def test_create_notification_uuid_format(self, mock_query):
        data = {"message": "test"}
        notif_id = await self.manager.create_notification("u1", data)
        
        self.assertTrue(notif_id.startswith("notif_"))
        # UUID hex length (12) + "notif_" (6) = 18
        self.assertEqual(len(notif_id), 18)

    @patch('Atlas.memory.neo4j_manager.Neo4jManager.query_graph', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.Neo4jManager.create_notification', new_callable=AsyncMock)
    async def test_due_scanner_cooldown(self, mock_create, mock_query):
        # 1. Mock query to return 1 task
        mock_query.side_effect = [
            [{"id": "t1", "text": "Task 1", "due_raw": "yarın"}], # scan_due_tasks query
            [{"updated": 1}] # update last_notified_at query
        ]
        mock_create.return_value = "notif_uuid"
        
        await scan_due_tasks("u1")
        
        # Verify notification created
        mock_create.assert_called_once()
        
        # Verify last_notified_at updated
        last_call = mock_query.call_args_list[-1]
        self.assertIn("SET t.last_notified_at = datetime()", last_call[0][0])

if __name__ == "__main__":
    unittest.main()
