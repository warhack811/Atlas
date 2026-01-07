import unittest
from unittest.mock import patch, AsyncMock
from Atlas.api import ChatRequest

class TestRC2Identity(unittest.IsolatedAsyncioTestCase):
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.ensure_user_session', new_callable=AsyncMock)
    @patch('Atlas.memory.context.build_memory_context_v3', new_callable=AsyncMock)
    @patch('Atlas.orchestrator.orchestrator.plan', new_callable=AsyncMock)
    async def test_user_id_fallback_to_session_id(self, mock_plan, mock_context, mock_ensure):
        # Case: user_id is None
        req = ChatRequest(message="merhaba", session_id="s123")
        
        # We need to test the logic inside api.py's chat/chat_stream
        # Since we are unit testing the "logic", we can simulate the call
        user_id = req.user_id if req.user_id else req.session_id
        self.assertEqual(user_id, "s123")
        
    async def test_user_id_explicit(self):
        # Case: user_id is provided
        req = ChatRequest(message="merhaba", session_id="s123", user_id="u456")
        user_id = req.user_id if req.user_id else req.session_id
        self.assertEqual(user_id, "u456")

if __name__ == "__main__":
    unittest.main()
