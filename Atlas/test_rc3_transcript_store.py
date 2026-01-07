import unittest
from unittest.mock import patch, AsyncMock
from Atlas.memory.neo4j_manager import Neo4jManager

class TestRC3TranscriptStore(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.manager = Neo4jManager()

    @patch('Atlas.memory.neo4j_manager.Neo4jManager.query_graph', new_callable=AsyncMock)
    async def test_append_turn(self, mock_query):
        mock_query.return_value = [{"index": 5}]
        index = await self.manager.append_turn("u1", "s1", "user", "merhaba")
        
        self.assertEqual(index, 5)
        args = mock_query.call_args[0]
        self.assertIn("CREATE (nt:Turn", args[0])
        self.assertIn("turn_index: turn_count", args[0])

    @patch('Atlas.memory.neo4j_manager.Neo4jManager.query_graph', new_callable=AsyncMock)
    async def test_get_recent_turns_order(self, mock_query):
        # Neo4j returns desc, but our method should return asc (chronological)
        mock_query.return_value = [
            {"role": "assistant", "content": "nasılsın", "turn_index": 1},
            {"role": "user", "content": "merhaba", "turn_index": 0}
        ]
        turns = await self.manager.get_recent_turns("u1", "s1", limit=2)
        
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0]["turn_index"], 0)
        self.assertEqual(turns[1]["turn_index"], 1)

    @patch('Atlas.memory.neo4j_manager.Neo4jManager.query_graph', new_callable=AsyncMock)
    async def test_count_turns(self, mock_query):
        mock_query.return_value = [{"total": 10}]
        count = await self.manager.count_turns("u1", "s1")
        self.assertEqual(count, 10)

if __name__ == "__main__":
    unittest.main()
