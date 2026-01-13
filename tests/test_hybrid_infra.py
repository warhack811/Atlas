import pytest
import os
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock
from Atlas.memory.context import build_chat_context_v1, _score_fuse_candidates
import Atlas.config

@pytest.mark.asyncio
async def test_hybrid_fusion_logic_unit(monkeypatch):
    """Verify weighted score fusion and recency decay (Unit)."""
    monkeypatch.setattr(Atlas.config, "HYBRID_WEIGHT_VECTOR", 0.4)
    monkeypatch.setattr(Atlas.config, "HYBRID_WEIGHT_GRAPH", 0.4)
    monkeypatch.setattr(Atlas.config, "HYBRID_WEIGHT_RECENCY", 0.2)
    monkeypatch.setattr(Atlas.config, "HYBRID_RECENCY_HALFLIFE_DAYS", 30.0)
    
    # Current time for recency
    now_iso = datetime.utcnow().isoformat()
    old_iso = "2020-01-01T00:00:00Z"
    
    candidates = [
        {
            "text": "Vector result", 
            "vector_score": 0.9, 
            "graph_score": 0.0, 
            "timestamp": old_iso,
            "source": "vector"
        },
        {
            "text": "Graph fact", 
            "vector_score": 0.0, 
            "graph_score": 0.8, 
            "timestamp": now_iso,
            "source": "graph"
        }
    ]
    
    fused = _score_fuse_candidates(candidates)
    # Graph score: 0.8*0.4 + 1.0*0.2 = 0.32 + 0.2 = 0.52
    # Vector score: 0.9*0.4 + ~0*0.2 = 0.36
    assert fused[1]["final_score"] > fused[0]["final_score"]

@pytest.mark.asyncio
async def test_hybrid_retrieval_integration_mocked(monkeypatch):
    """Verify build_chat_context_v1 calls both sources and fuses result (Deterministic)."""
    monkeypatch.setattr(Atlas.config, "ENABLE_HYBRID_RETRIEVAL", True)
    
    mock_embedder = MagicMock()
    mock_embedder.embed = AsyncMock(return_value=[0.1]*768)
    
    with patch("Atlas.memory.context._build_hybrid_candidates_vector") as mock_v, \
         patch("Atlas.memory.context._build_hybrid_candidates_graph") as mock_g, \
         patch("Atlas.memory.neo4j_manager.neo4j_manager.get_recent_turns", AsyncMock(return_value=[])), \
         patch("Atlas.memory.neo4j_manager.neo4j_manager.get_user_memory_mode", AsyncMock(return_value="STD")):
        
        # Ensure 'timestamp' is present to avoid KeyError in fuse
        mock_v.return_value = [{
            "text": "V-Fact", "vector_score": 0.9, "graph_score": 0.0, 
            "timestamp": "2024-01-01T00:00:00Z", "source": "vector"
        }]
        mock_g.return_value = [{
            "text": "G-Fact", "vector_score": 0.0, "graph_score": 0.8, 
            "timestamp": "2024-01-01T00:00:00Z", "source": "graph"
        }]
        
        context = await build_chat_context_v1("user_test", "s1", "hi", embedder=mock_embedder)
        
        assert "Hibrit Hafıza" in context
        assert "V-Fact" in context
        assert "G-Fact" in context
