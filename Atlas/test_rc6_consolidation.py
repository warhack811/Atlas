import unittest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from Atlas.memory.neo4j_manager import Neo4jManager
from Atlas.scheduler import run_consolidation_worker

class TestRC6Consolidation(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mgr = Neo4jManager()

    @patch('Atlas.memory.neo4j_manager.Neo4jManager.query_graph', new_callable=AsyncMock)
    async def test_create_consolidation_pending(self, mock_query):
        await self.mgr.create_consolidation_pending("s1", 10, 7)
        args, _ = mock_query.call_args
        self.assertIn("kind: 'CONSOLIDATED'", args[0])
        self.assertEqual(args[1]["sid"], "s1")
        self.assertEqual(args[1]["window"], 10)

    @patch('Atlas.scheduler._IS_LEADER', True)
    @patch('Atlas.memory.neo4j_manager.Neo4jManager.query_graph', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.Neo4jManager.claim_pending_consolidation', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.Neo4jManager.get_episodes_by_ids', new_callable=AsyncMock)
    @patch('Atlas.scheduler.generate_response', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.Neo4jManager.mark_episode_ready', new_callable=AsyncMock)
    async def test_run_consolidation_worker(self, mock_ready, mock_gen, mock_get_ep, mock_claim, mock_query):
        # Setup mocks
        mock_query.return_value = [{"id": "s1"}]
        mock_claim.return_value = {"id": "c1", "source_ids": ["e1", "e2"]}
        mock_get_ep.return_value = [{"summary": "sum1"}, {"summary": "sum2"}]
        
        mock_gen.return_value = MagicMock(ok=True, text="Consolidated Summary", model="gemini-test")
        
        # Run
        await run_consolidation_worker()
        
        # Verify
        mock_ready.assert_called_once()
        args, kwargs = mock_ready.call_args
        self.assertEqual(args[0], "c1")
        self.assertEqual(args[1], "Consolidated Summary")
        self.assertEqual(args[2], "gemini-test")

if __name__ == "__main__":
    unittest.main()
