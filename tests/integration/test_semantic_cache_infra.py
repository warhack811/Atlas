import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import BackgroundTasks
from atlas.api import chat, ChatRequest
import atlas.config
import atlas.api

@pytest.mark.asyncio
async def test_semantic_cache_user_isolation_deterministic(monkeypatch):
    """Verify that user A cannot hit user B's cache (Deterministic)."""
    monkeypatch.setattr(Atlas.config, "ENABLE_SEMANTIC_CACHE", True)
    monkeypatch.setattr(Atlas.api, "ENABLE_SEMANTIC_CACHE", True)
    
    # We need a real BackgroundTasks object or a mock that has add_task
    bg = BackgroundTasks()
    
    with patch("atlas.api.semantic_cache") as mock_cache, \
         patch("atlas.core.governance.safety.safety_gate.check_input_safety", AsyncMock(return_value=(True, "merhaba", [], "m"))), \
         patch("atlas.memory.neo4j_manager.neo4j_manager.ensure_user_session", AsyncMock()), \
         patch("atlas.memory.neo4j_manager.neo4j_manager.append_turn", AsyncMock()), \
         patch("atlas.memory.neo4j_manager.neo4j_manager.count_turns", new_callable=AsyncMock) as mock_count, \
         patch("atlas.memory.extractor.extract_and_save", AsyncMock()): # Mock background task itself

        mock_count.return_value = 0

        async def mock_get_with_meta(uid, q):
            if uid == "user_a":
                return {"response": "A's cached response", "similarity": 0.99, "latency_ms": 5}
            return {"response": None, "similarity": 0.0, "latency_ms": 1}
            
        mock_cache.get_with_meta = AsyncMock(side_effect=mock_get_with_meta)
        
        req_b = ChatRequest(message="merhaba", user_id="user_b", session_id="s_b")
        
        with patch("atlas.core.orchestrator.orchestrator.plan") as mock_plan, \
             patch("atlas.core.dag_executor.dag_executor.execute_plan", AsyncMock(return_value=[])), \
             patch("atlas.services.synthesizer.synthesizer.synthesize", AsyncMock(return_value=("resp", "m", "p", {}))):
            
            mock_plan.return_value = MagicMock(active_intent="chat", reasoning="test", rewritten_query="merhaba", user_thought="test")
            
            res_b = await chat(req_b, bg, {"username": "user_b"})
            assert res_b.response == "resp"
            assert mock_plan.called

@pytest.mark.asyncio
async def test_cache_hit_metadata_and_skip_refined(monkeypatch):
    """Verify metadata and LLM skip on cache hit."""
    monkeypatch.setattr(Atlas.api, "ENABLE_SEMANTIC_CACHE", True)
    bg = BackgroundTasks()
    
    with patch("atlas.api.semantic_cache") as mock_cache, \
         patch("atlas.core.governance.safety.safety_gate.check_input_safety", AsyncMock(return_value=(True, "test", [], "m"))), \
         patch("atlas.memory.neo4j_manager.neo4j_manager.ensure_user_session", AsyncMock()), \
         patch("atlas.memory.neo4j_manager.neo4j_manager.append_turn", AsyncMock()), \
         patch("atlas.memory.neo4j_manager.neo4j_manager.count_turns", new_callable=AsyncMock) as mock_count:

        mock_count.return_value = 0
        
        mock_cache.get_with_meta = AsyncMock(return_value={
            "response": "cached answer", "similarity": 0.95, "latency_ms": 10
        })
        
        req = ChatRequest(message="test", user_id="user_a", session_id="s1")
        
        with patch("atlas.core.orchestrator.orchestrator.plan") as mock_plan:
            res = await chat(req, bg, {"username": "user_a"})
            assert res.response == "cached answer"
            assert not mock_plan.called
            assert res.rdr["metadata"]["cache"]["hit"] is True
