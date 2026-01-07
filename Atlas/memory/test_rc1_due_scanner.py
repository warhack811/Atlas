import unittest
from unittest.mock import patch, AsyncMock
from Atlas.memory.due_scanner import scan_due_tasks

class TestRC1DueScanner(unittest.IsolatedAsyncioTestCase):

    @patch('Atlas.memory.neo4j_manager.Neo4jManager.query_graph', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.Neo4jManager.create_notification', new_callable=AsyncMock)
    async def test_scan_tasks_includes_cooldown_and_counter(self, mock_create, mock_query):
        # Mock finding 1 task
        mock_query.side_effect = [
            [{"id": "t1", "text": "Task 1", "due_raw": "yarın", "due_dt_obj": "2026-01-08T10:00:00Z"}], # Selection query
            [{"updated": 1}] # Update query
        ]
        mock_create.return_value = "notif_uuid"
        
        await scan_due_tasks("u1")
        
        # 1. Verify selection query structure (cooldown check)
        selection_call = mock_query.call_args_list[0]
        query_text = selection_call[0][0]
        self.assertIn("duration('PT60M')", query_text)
        self.assertIn("t.last_notified_at < datetime()", query_text)
        
        # 2. Verify update query structure (counter and last_notified_at)
        update_call = mock_query.call_args_list[1]
        update_query = update_call[0][0]
        self.assertIn("SET t.last_notified_at = datetime()", update_query)
        self.assertIn("t.notified_count = coalesce(t.notified_count, 0) + 1", update_query)
        
        # 3. Verify notification reason explainability
        notif_call = mock_create.call_args
        notif_data = notif_call[0][1]
        self.assertIn("Task deadline reached at", notif_data["reason"])
        self.assertEqual(notif_data["related_task_id"], "t1")

if __name__ == "__main__":
    unittest.main()
