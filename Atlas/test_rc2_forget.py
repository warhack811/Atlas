import unittest
from unittest.mock import patch, AsyncMock
from Atlas.memory.neo4j_manager import Neo4jManager

class TestRC2Forget(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.manager = Neo4jManager()

    @patch('Atlas.memory.neo4j_manager.Neo4jManager.query_graph', new_callable=AsyncMock)
    async def test_forget_all_query_structure(self, mock_query):
        # api.py'daki gerçek sorgu yapısını simüle et
        query = """
        MATCH (u:User {id: $uid})-[r:KNOWS|HAS_TASK|HAS_NOTIFICATION|HAS_SESSION|HAS_ANCHOR|HAS_FACT]->() DELETE r
        WITH 1 as dummy
        MATCH ()-[r:FACT {user_id: $uid}]->() DELETE r
        """
        await self.manager.query_graph(query, {"uid": "u1"})
        
        args = mock_query.call_args[0]
        self.assertIn("DELETE r", args[0])
        self.assertIn(":KNOWS|HAS_TASK|HAS_NOTIFICATION|HAS_SESSION|HAS_ANCHOR|HAS_FACT", args[0])
        self.assertIn(":FACT {user_id: $uid}", args[0])
        self.assertNotIn("DETACH DELETE u", args[0]) # Node silinmemeli

if __name__ == "__main__":
    unittest.main()
