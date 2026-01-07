import unittest
from unittest.mock import patch, AsyncMock, MagicMock
from Atlas.api import chat, ChatRequest

class TestRC3EpisodeTrigger(unittest.IsolatedAsyncioTestCase):
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.ensure_user_session', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.append_turn', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.count_turns', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.create_episode', new_callable=AsyncMock)
    @patch('Atlas.orchestrator.orchestrator.plan', new_callable=AsyncMock)
    @patch('Atlas.dag_executor.dag_executor.execute_plan', new_callable=AsyncMock)
    @patch('Atlas.synthesizer.synthesizer.synthesize', new_callable=AsyncMock)
    @patch('Atlas.rdr.save_rdr')
    async def test_episode_trigger_at_20_turns(self, mock_rdr, mock_synth, mock_exec, mock_plan, mock_ep, mock_count, mock_append, mock_ensure):
        # Mocking for chat endpoint
        mock_count.return_value = 20 # Trigger threshold
        mock_synth.return_value = ("Yapay zeka yanıtı", "model-x", "prompt", {"persona": "default"})
        mock_exec.return_value = []
        mock_plan.return_value = MagicMock(tasks=[], active_intent="test", user_thought="Düşünüyorum...")
        
        request = ChatRequest(message="hello", session_id="s20")
        
        # BackgroundTasks nesnesini mockla
        mock_bt = MagicMock()
        
        # Direkt fonksiyonu çağır
        await chat(request, mock_bt)
        
        # Verify create_episode was called because count == 20
        self.assertTrue(mock_ep.called)
        # Check if turn numbers are in args
        # call_args sequence: (user_id, session_id, summary, start, end)
        args, kwargs = mock_ep.call_args
        self.assertEqual(args[3], 1) # start_turn (20 - 19 = 1)
        self.assertEqual(args[4], 20) # end_turn

if __name__ == "__main__":
    unittest.main()
