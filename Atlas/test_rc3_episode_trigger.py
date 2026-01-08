import unittest
from unittest.mock import patch, AsyncMock
from Atlas.api import _maybe_trigger_episodic_memory

class TestRC3EpisodeTrigger(unittest.IsolatedAsyncioTestCase):
    """
    RC-3 Episodic Trigger testinin RC-4 standardına göre stabilizasyonu.
    Helper fonksiyonu direkt test ederek event loop çakışmalarını önler.
    """

    @patch('Atlas.memory.neo4j_manager.neo4j_manager.count_turns', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.create_episode_pending', new_callable=AsyncMock)
    async def test_trigger_at_20_turns(self, mock_create, mock_count):
        # Case 1: Tam 20 turn olduğunda tetiklenmeli
        mock_count.return_value = 20
        await _maybe_trigger_episodic_memory("user_1", "session_1")
        
        self.assertTrue(mock_create.called)
        args, _ = mock_create.call_args
        # create_episode_pending(user_id, session_id, start_turn, end_turn)
        self.assertEqual(args[2], 1)  # start_turn (20-19)
        self.assertEqual(args[3], 20) # end_turn

    @patch('Atlas.memory.neo4j_manager.neo4j_manager.count_turns', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.create_episode_pending', new_callable=AsyncMock)
    async def test_no_trigger_at_19_turns(self, mock_create, mock_count):
        # Case 2: 19 turn olduğunda tetiklenmemeli
        mock_count.return_value = 19
        await _maybe_trigger_episodic_memory("user_1", "session_1")
        
        self.assertFalse(mock_create.called)

if __name__ == "__main__":
    unittest.main()
