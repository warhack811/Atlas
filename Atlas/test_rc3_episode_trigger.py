import unittest
from unittest.mock import patch, AsyncMock, MagicMock
import asyncio
from Atlas.api import chat, ChatRequest

class TestRC3EpisodeTrigger(unittest.TestCase):
    """Event-loop sorunlarını aşmak için asyncio.run kullanan izole test."""

    @patch('Atlas.memory.neo4j_manager.neo4j_manager.ensure_user_session', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.append_turn', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.count_turns', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.create_episode_pending', new_callable=AsyncMock)
    @patch('Atlas.orchestrator.orchestrator.plan', new_callable=AsyncMock)
    @patch('Atlas.dag_executor.dag_executor.execute_plan', new_callable=AsyncMock)
    @patch('Atlas.synthesizer.synthesizer.synthesize', new_callable=AsyncMock)
    @patch('Atlas.rdr.save_rdr')
    def test_episode_trigger_at_20_turns(self, mock_rdr, mock_synth, mock_exec, mock_plan, mock_ep, mock_count, mock_append, mock_ensure):
        
        async def run_async_test():
            # Setup
            mock_count.return_value = 20
            mock_synth.return_value = ("Yanıt", "model-x", "prompt", {"persona": "default"})
            mock_exec.return_value = []
            mock_plan.return_value = MagicMock(active_intent="test", user_thought="...")
            
            request = ChatRequest(message="merhaba", session_id="s_test")
            mock_bt = MagicMock()
            
            # Action
            await chat(request, mock_bt)
            
            # Assert
            return mock_ep.called, mock_ep.call_args

        # Run in a clean loop
        called, call_args = asyncio.run(run_async_test())
        
        # Final Assertions
        self.assertTrue(called)
        args, kwargs = call_args
        self.assertEqual(args[2], 1)
        self.assertEqual(args[3], 20)

if __name__ == "__main__":
    unittest.main()
