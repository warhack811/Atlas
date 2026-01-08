import unittest
import asyncio
from unittest.mock import patch, MagicMock
from Atlas.api import ChatRequest
from fastapi.testclient import TestClient
from Atlas.api import app

class TestRC9ApiDebugTrace(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("Atlas.config.DEBUG", False)
    @patch("Atlas.safety.safety_gate.check_input_safety")
    def test_debug_trace_hidden_if_debug_false(self, mock_safety):
        mock_safety.return_value = asyncio.Future()
        mock_safety.return_value.set_result((True, "Test", [], "model"))
        
        # Mock context building to avoid DB calls
        with patch("Atlas.memory.context.build_memory_context_v3", return_value=asyncio.Future()) as mock_ctx:
            mock_ctx.return_value.set_result("mocked context")
            
            response = self.client.post("/api/chat", json={
                "message": "Test",
                "session_id": "s1",
                "debug_trace": True
            })
            
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertIsNone(data.get("debug_trace"))

    @patch("Atlas.config.DEBUG", True)
    @patch("Atlas.safety.safety_gate.check_input_safety")
    def test_debug_trace_visible_if_debug_true(self, mock_safety):
        mock_safety.return_value = asyncio.Future()
        mock_safety.return_value.set_result((True, "Test", [], "model"))
        
        from Atlas.memory.trace import ContextTrace
        mock_trace = ContextTrace(request_id="t1", user_id="u1", session_id="s1")
        
        with patch("Atlas.memory.context.build_memory_context_v3", return_value=asyncio.Future()) as mock_ctx:
            mock_ctx.return_value.set_result("mocked context")
            
            # build_chat_context_v1'i de mocklayalım ki trace dönebilsin
            with patch("Atlas.memory.context.build_chat_context_v1", return_value=asyncio.Future()) as mock_chat_ctx:
                mock_chat_ctx.return_value.set_result("mocked chat context")
                
                # FastAPI chat endpoint'ini çağırdığımızda build_memory_context_v3 çağrılır
                # ve api.py içindeki trace objesi oradan beslenir.
                # Ancak api.py içindeki trace objesini yakalamak için build_chat_context_v1'i 
                # trace parametresiyle çağırdığımızı doğrulamalıyız.
                
                response = self.client.post("/api/chat", json={
                    "message": "Test",
                    "session_id": "s1",
                    "debug_trace": True
                })
                
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertIsNotNone(data.get("debug_trace"))
                self.assertEqual(data["debug_trace"]["user_id"], "s1") # user_id default session_id olur api'de

if __name__ == "__main__":
    unittest.main()
