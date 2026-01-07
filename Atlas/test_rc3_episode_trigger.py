import unittest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient
from Atlas.api import app

class TestRC3EpisodeTrigger(unittest.IsolatedAsyncioTestCase):
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.ensure_user_session', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.append_turn', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.count_turns', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.create_episode', new_callable=AsyncMock)
    @patch('Atlas.orchestrator.orchestrator.plan', new_callable=AsyncMock)
    @patch('Atlas.dag_executor.dag_executor.execute_plan', new_callable=AsyncMock)
    @patch('Atlas.synthesizer.synthesizer.synthesize', new_callable=AsyncMock)
    async def test_episode_trigger_at_20_turns(self, mock_synth, mock_exec, mock_plan, mock_ep, mock_count, mock_append, mock_ensure):
        # Mocking for chat endpoint
        mock_count.return_value = 20 # Trigger threshold
        mock_synth.return_value = ("Yapay zeka yanıtı", "model-x")
        mock_exec.return_value = []
        mock_plan.return_value = MagicMock(tasks=[], active_intent="test")
        
        from httpx import ASGITransport
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            payload = {"message": "hello", "session_id": "s20"}
            response = await ac.post("/api/chat", json=payload)
        
        self.assertEqual(response.status_code, 200)
        # Verify create_episode was called because count == 20
        self.assertTrue(mock_ep.called)
        # Check if turn numbers are in args
        call_args_str = str(mock_ep.call_args)
        self.assertIn("20", call_args_str)

if __name__ == "__main__":
    unittest.main()
