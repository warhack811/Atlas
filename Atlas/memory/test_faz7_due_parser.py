import unittest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime
from Atlas.memory.prospective_store import create_task

class TestDueParser(unittest.IsolatedAsyncioTestCase):

    @patch('Atlas.memory.neo4j_manager.neo4j_manager.query_graph', new_callable=AsyncMock)
    async def test_create_task_with_relative_date(self, mock_query):
        # Case: "yarın" parsing
        mock_query.return_value = [{"task_id": "t1"}]
        
        task_id = await create_task("user123", "Toplantı", due_at="yarın")
        
        self.assertIsNotNone(task_id)
        args = mock_query.call_args[0]
        params = args[1]
        
        self.assertEqual(params["due_at_raw"], "yarın")
        self.assertIsNotNone(params["due_at_dt"])
        
        # Verify it's a future date
        from datetime import timezone
        due_dt = datetime.fromisoformat(params["due_at_dt"].replace('Z', '+00:00'))
        self.assertTrue(due_dt > datetime.now(timezone.utc))

    @patch('Atlas.memory.neo4j_manager.neo4j_manager.query_graph', new_callable=AsyncMock)
    async def test_create_task_with_specific_date(self, mock_query):
        # Case: "15 ocak 14:00" parsing
        mock_query.return_value = [{"task_id": "t2"}]
        
        task_id = await create_task("user123", "Doktor randevusu", due_at="15 ocak 14:00")
        
        args = mock_query.call_args[0]
        params = args[1]
        
        due_dt = datetime.fromisoformat(params["due_at_dt"].replace('Z', '+00:00'))
        self.assertEqual(due_dt.month, 1)
        self.assertEqual(due_dt.day, 15)
        self.assertEqual(due_dt.hour, 14)

    @patch('Atlas.memory.neo4j_manager.neo4j_manager.query_graph', new_callable=AsyncMock)
    async def test_create_task_invalid_date(self, mock_query):
        # Case: invalid date string
        mock_query.return_value = [{"task_id": "t3"}]
        
        task_id = await create_task("user123", "Bir şey yap", due_at="belirsiz bir zaman")
        
        args = mock_query.call_args[0]
        params = args[1]
        
        self.assertEqual(params["due_at_raw"], "belirsiz bir zaman")
        self.assertIsNone(params["due_at_dt"])

if __name__ == "__main__":
    unittest.main()
