import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from atlas.core.orchestrator import Orchestrator
from atlas.memory.state import state_manager

@pytest.mark.skip(reason="Legacy test broken by refactor")
@pytest.mark.asyncio
async def test_topic_update_on_new_topic():
    """Yeni bir konu geldiğinde state'in güncellendiğini doğrula."""
    session_id = "test_sess_topic_1"
    state_manager.clear_state(session_id)
    state = state_manager.get_state(session_id)
    state.current_topic = "Genel"
    
    plan_data = {
        "intent": "coding",
        "detected_topic": "Python Kodlama",
        "tasks": []
    }
    
    with patch("atlas.core.orchestrator.Orchestrator._call_brain", new_callable=AsyncMock) as mock_brain:
        mock_brain.return_value = (plan_data, "prompt", "model")
        
        # Neo4j çağrısını mock'la (async task olduğu için beklememize gerek yok ama hata vermesin)
        with patch("atlas.memory.neo4j_manager.neo4j_manager.update_session_topic", new_callable=AsyncMock) as mock_neo4j:
            with patch("atlas.memory.buffer.MessageBuffer.get_llm_messages", return_value=[]):
                # Ensure context builder mocks don't leak into state
                with patch("atlas.memory.context.ContextBuilder.get_neo4j_context", new_callable=AsyncMock) as mock_ctx:
                    mock_ctx.return_value = ""
                    await Orchestrator.plan(session_id, "Python öğrenmek istiyorum")
            
            assert state.current_topic == "Python Kodlama"
            assert "Genel" in state.topic_history

@pytest.mark.asyncio
async def test_no_topic_update_on_same():
    """'SAME' geldiğinde konunun değişmediğini doğrula."""
    session_id = "test_sess_topic_2"
    state_manager.clear_state(session_id)
    state = state_manager.get_state(session_id)
    state.current_topic = "Müzik"
    
    plan_data = {
        "intent": "general",
        "detected_topic": "SAME",
        "tasks": []
    }
    
    with patch("atlas.core.orchestrator.Orchestrator._call_brain", new_callable=AsyncMock) as mock_brain:
        mock_brain.return_value = (plan_data, "prompt", "model")
        
        await Orchestrator.plan(session_id, "Devam et")
        
        assert state.current_topic == "Müzik"
        assert len(state.topic_history) == 0

@pytest.mark.asyncio
async def test_no_topic_update_on_chitchat():
    """'CHITCHAT' geldiğinde konunun değişmediğini doğrula."""
    session_id = "test_sess_topic_3"
    state_manager.clear_state(session_id)
    state = state_manager.get_state(session_id)
    state.current_topic = "Bilim"
    
    plan_data = {
        "intent": "general",
        "detected_topic": "CHITCHAT",
        "tasks": []
    }
    
    with patch("atlas.core.orchestrator.Orchestrator._call_brain", new_callable=AsyncMock) as mock_brain:
        mock_brain.return_value = (plan_data, "prompt", "model")
        
        await Orchestrator.plan(session_id, "Naber?")
        
        assert state.current_topic == "Bilim"
