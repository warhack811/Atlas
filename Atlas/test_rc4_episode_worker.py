import unittest
from unittest.mock import patch, AsyncMock, MagicMock
from Atlas.scheduler import run_episode_worker

class TestRC4EpisodeWorker(unittest.IsolatedAsyncioTestCase):
    """Episode Worker (background job) testleri."""

    @patch('Atlas.scheduler._IS_LEADER', True)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.claim_pending_episode', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.get_recent_turns', new_callable=AsyncMock)
    @patch('Atlas.scheduler.generate_response', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.mark_episode_ready', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.mark_episode_failed', new_callable=AsyncMock)
    async def test_worker_processes_episode_successfully(self, mock_fail, mock_ready, mock_gen, mock_turns, mock_claim):
        # Setup: Claim 1 pending episode
        mock_claim.return_value = {
            "id": "ep1", "user_id": "u1", "session_id": "s1", "start_turn": 1, "end_turn": 20
        }
        # Mock turns
        mock_turns.return_value = [
            {"turn_index": 1, "role": "user", "content": "hi"},
            {"turn_index": 20, "role": "assistant", "content": "hello"}
        ]
        # Mock LLM
        mock_gen.return_value = MagicMock(ok=True, text="Summary draft", model="gemini-flash")
        
        # Action
        await run_episode_worker()
        
        # Verify: mark_episode_ready çağrıldı mı?
        self.assertTrue(mock_ready.called)
        self.assertFalse(mock_fail.called)
        args, kwargs = mock_ready.call_args
        self.assertEqual(args[0], "ep1")
        self.assertEqual(args[1], "Summary draft")

if __name__ == "__main__":
    unittest.main()
