import unittest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from Atlas.memory.neo4j_manager import Neo4jManager

class TestRC6Pruning(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mgr = Neo4jManager()

    @patch('Atlas.memory.neo4j_manager.Neo4jManager.query_graph', new_callable=AsyncMock)
    async def test_prune_turns(self, mock_query):
        await self.mgr.prune_turns(30, 400)
        # 2 query çağrılmalı: biri time-based, biri limit-based
        self.assertEqual(mock_query.call_count, 2)
        
        # İlk çağrı (time-based) kontrolü
        args, _ = mock_query.call_args_list[0]
        self.assertIn("datetime() - duration('P' + toString($days) + 'D')", args[0])
        self.assertEqual(args[1]["days"], 30)

    @patch('Atlas.memory.neo4j_manager.Neo4jManager.query_graph', new_callable=AsyncMock)
    async def test_prune_notifications(self, mock_query):
        await self.mgr.prune_notifications(30)
        args, _ = mock_query.call_args
        self.assertIn("n.read = true", args[0])
        self.assertIn("n.created_at < datetime()", args[0])
        self.assertEqual(args[1]["days"], 30)

    @patch('Atlas.memory.neo4j_manager.Neo4jManager.query_graph', new_callable=AsyncMock)
    async def test_prune_tasks(self, mock_query):
        await self.mgr.prune_tasks(30)
        args, _ = mock_query.call_args
        self.assertIn("task.status IN ['DONE', 'CLOSED']", args[0])
        self.assertEqual(args[1]["days"], 30)

if __name__ == "__main__":
    unittest.main()
