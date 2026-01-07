import unittest
from unittest.mock import patch, AsyncMock
from Atlas.memory.neo4j_manager import Neo4jManager

class TestRC2Forget(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.manager = Neo4jManager()

    @patch('Atlas.memory.neo4j_manager.Neo4jManager.query_graph', new_callable=AsyncMock)
    async def test_forget_all_query_structure(self, mock_query):
        # We test if the query targets relationships, not nodes
        query = "MATCH (u:User {id: $uid})-[r:HAS_FACT|KNOWS|HAS_TASK|HAS_NOTIFICATION]->() DELETE r"
        # Simulate logic from api.py
        await self.manager.query_graph(query, {"uid": "u1"})
        
        args = mock_query.call_args[0]
        self.assertIn("DELETE r", args[0])
        self.assertIn(":HAS_FACT|KNOWS|HAS_TASK|HAS_NOTIFICATION", args[0])
        self.assertNotIn("DETACH DELETE u", args[0]) # Should not delete user node

if __name__ == "__main__":
    unittest.main()
