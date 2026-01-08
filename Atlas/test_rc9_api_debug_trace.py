import unittest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from Atlas.api import app

class TestRC9ApiDebugTrace(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("Atlas.config.DEBUG", True)
    @patch("Atlas.safety.safety_gate.check_input_safety")
    @patch("Atlas.memory.neo4j_manager.neo4j_manager.ensure_user_session")
    @patch("Atlas.memory.neo4j_manager.neo4j_manager.append_turn")
    @patch("Atlas.memory.context.build_chat_context_v1")
    @patch("Atlas.orchestrator.orchestrator.plan")
    @patch("Atlas.dag_executor.dag_executor.execute_plan")
    @patch("Atlas.synthesizer.synthesizer.synthesize")
    def test_debug_trace_visible_if_requested(self, mock_synth, mock_exec, mock_plan, mock_ctx, mock_app, mock_ens, mock_saf):
        # Async functions need AsyncMock as side_effect or return_value
        mock_saf.side_effect = AsyncMock(return_value=(True, "hello", [], "model"))
        mock_ctx.side_effect = AsyncMock(return_value="mocked context")
        mock_ens.side_effect = AsyncMock(return_value=None)
        mock_app.side_effect = AsyncMock(return_value=None)
        
        from Atlas.orchestrator import OrchestrationPlan
        mock_plan.side_effect = AsyncMock(return_value=OrchestrationPlan(tasks=[], active_intent="general", is_follow_up=False, context_focus=""))
        
        mock_exec.side_effect = AsyncMock(return_value=[])
        mock_synth.side_effect = AsyncMock(return_value=("response", "model", "prompt", {}))
        
        response = self.client.post("/api/chat", json={
            "message": "hello",
            "session_id": "s1",
            "debug_trace": True
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("debug_trace", data)
        self.assertIsNotNone(data["debug_trace"])

    @patch("Atlas.config.DEBUG", False)
    def test_debug_trace_hidden_if_debug_false(self):
        # Diğer mocklara gerek yok çünkü debug_trace: True gelse bile 
        # api.py'da DEBUG check'i hemen başta (chat'in içinde değil ama ContextTrace init kısmında) yapılıyor.
        # Aslında chat metodunun içine girmeden önce ChatRequest parse ediliyor.
        # Chat metodunun içinde trace objesi DEBUG check ile oluşuyor.
        
        # Sadece niyet analizi seviyesine kadar mocklayalım ki hata vermesin
        with patch("Atlas.safety.safety_gate.check_input_safety", side_effect=AsyncMock(return_value=(True, "hello", [], "model"))):
            with patch("Atlas.memory.neo4j_manager.neo4j_manager.ensure_user_session", side_effect=AsyncMock(return_value=None)):
                with patch("Atlas.memory.neo4j_manager.neo4j_manager.append_turn", side_effect=AsyncMock(return_value=None)):
                    with patch("Atlas.memory.context.build_chat_context_v1", side_effect=AsyncMock(return_value="")):
                        from Atlas.orchestrator import OrchestrationPlan
                        with patch("Atlas.orchestrator.orchestrator.plan", side_effect=AsyncMock(return_value=OrchestrationPlan(tasks=[], active_intent="general", is_follow_up=False, context_focus=""))):
                            with patch("Atlas.dag_executor.dag_executor.execute_plan", side_effect=AsyncMock(return_value=[])):
                                with patch("Atlas.synthesizer.synthesizer.synthesize", side_effect=AsyncMock(return_value=("res", "m", "p", {}))):
                                    response = self.client.post("/api/chat", json={
                                        "message": "hello",
                                        "session_id": "s1",
                                        "debug_trace": True
                                    })
                                    
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data.get("debug_trace"))

if __name__ == "__main__":
    unittest.main()
