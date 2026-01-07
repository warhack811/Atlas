import unittest
from unittest.mock import patch, AsyncMock, MagicMock
import asyncio

class TestRC3EpisodeTrigger(unittest.TestCase):
    """
    Extremely isolated test for RC-3 Episode Trigger.
    """

    @patch('Atlas.memory.neo4j_manager.neo4j_manager.ensure_user_session', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.append_turn', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.count_turns', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.create_episode_pending', new_callable=AsyncMock)
    @patch('Atlas.orchestrator.orchestrator.plan', new_callable=AsyncMock)
    @patch('Atlas.dag_executor.dag_executor.execute_plan', new_callable=AsyncMock)
    @patch('Atlas.synthesizer.synthesizer.synthesize', new_callable=AsyncMock)
    @patch('Atlas.rdr.save_rdr')
    def test_episode_trigger_at_20_turns(self, mock_rdr, mock_synth, mock_exec, mock_plan, mock_ep, mock_count, mock_append, mock_ensure):
        
        # Local import to avoid top-level loop issues
        from Atlas.api import chat, ChatRequest
        
        async def run_test():
            mock_count.return_value = 20
            mock_synth.return_value = ("Yanıt", "model-x", "prompt", {"persona": "default"})
            mock_exec.return_value = []
            
            plan_mock = MagicMock()
            plan_mock.active_intent = "test"
            plan_mock.user_thought = "..."
            mock_plan.return_value = plan_mock
            
            request = ChatRequest(message="hello", session_id="s_test")
            mock_bt = MagicMock()
            
            await chat(request, mock_bt)
            return mock_ep.called, mock_ep.call_args

        # Use a new loop to be sure
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            called, call_args = loop.run_until_complete(run_test())
        finally:
            loop.close()

        self.assertTrue(called)
        args, kwargs = call_args
        self.assertEqual(args[2], 1)
        self.assertEqual(args[3], 20)

if __name__ == "__main__":
    unittest.main()
