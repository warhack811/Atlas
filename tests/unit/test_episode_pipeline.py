"""
Episode Pipeline Integration Tests

Tests for Y.4 Episode Embedding Pipeline:
- Gemini embedding generation
- Qdrant upsert with user isolation
- Neo4j metadata tracking (vector_status, vector_error)
- Graceful degradation on failures
"""

import pytest
import os
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

from Atlas.memory.episode_pipeline import finalize_episode_with_vectors


@pytest.mark.asyncio
async def test_finalize_episode_success():
    """
    Happy path: Summary → Embedding → Qdrant → Neo4j
    
    WHY: Validates end-to-end pipeline with all components working.
    """
    # Mock dependencies
    with patch('Atlas.memory.episode_pipeline.GeminiEmbedder') as MockEmbedder, \
         patch('Atlas.memory.episode_pipeline.QdrantManager') as MockQdrant, \
         patch('Atlas.memory.episode_pipeline.Neo4jManager') as MockNeo4j, \
         patch('Atlas.memory.episode_pipeline.BYPASS_VECTOR_SEARCH', False):
        
        # Setup mocks
        mock_embedder = MockEmbedder.return_value
        mock_embedder.embed = AsyncMock(return_value=[0.1] * 768)
        
        mock_qdrant = MockQdrant.return_value
        mock_qdrant.upsert_episode = AsyncMock(return_value=True)
        
        mock_neo4j = MockNeo4j.return_value
        mock_neo4j.mark_episode_ready = AsyncMock()
        
        # Execute
        result = await finalize_episode_with_vectors(
            episode_id="test_ep_001",
            user_id="test_user",
            session_id="test_session",
            summary="This is a test episode summary with sufficient length.",
            model="gemini-2.0-flash",
            wait_for_qdrant=False
        )
        
        # Assert
        assert result["status"] == "success"
        assert result["vector_status"] == "READY"
        assert result["embedding_model"] == "models/text-embedding-004"
        assert result["error"] is None
        
        # Verify calls
        mock_embedder.embed.assert_called_once()
        mock_qdrant.upsert_episode.assert_called_once()
        mock_neo4j.mark_episode_ready.assert_called_once()
        
        # Verify Neo4j was called with correct vector_status
        call_args = mock_neo4j.mark_episode_ready.call_args
        assert call_args.kwargs["vector_status"] == "READY"
        assert call_args.kwargs["vector_error"] is None


@pytest.mark.asyncio
async def test_finalize_episode_short_summary():
    """
    Summary too short: Skip vector processing, episode still READY
    
    WHY: Edge case - graceful handling of insufficient content.
    """
    with patch('Atlas.memory.episode_pipeline.Neo4jManager') as MockNeo4j:
        mock_neo4j = MockNeo4j.return_value
        mock_neo4j.mark_episode_ready = AsyncMock()
        
        result = await finalize_episode_with_vectors(
            episode_id="test_ep_002",
            user_id="test_user",
            session_id="test_session",
            summary="Short",  # Less than min_summary_length (10)
            model="gemini-2.0-flash",
            min_summary_length=10
        )
        
        assert result["status"] == "success"
        assert result["vector_status"] == "SKIPPED"
        assert "too short" in result["error"].lower()
        
        # Neo4j should still be updated
        mock_neo4j.mark_episode_ready.assert_called_once()
        call_args = mock_neo4j.mark_episode_ready.call_args
        assert call_args.kwargs["vector_status"] == "SKIPPED"


@pytest.mark.asyncio
async def test_finalize_episode_embedding_failure():
    """
    Embedding generation fails: Episode READY, vector_status=FAILED
    
    WHY: Production resilience - don't block episode completion on vector errors.
    """
    with patch('Atlas.memory.episode_pipeline.GeminiEmbedder') as MockEmbedder, \
         patch('Atlas.memory.episode_pipeline.Neo4jManager') as MockNeo4j, \
         patch('Atlas.memory.episode_pipeline.BYPASS_VECTOR_SEARCH', False):
        
        # Embedding fails
        mock_embedder_instance = MockEmbedder.return_value
        mock_embedder_instance.embed = AsyncMock(side_effect=RuntimeError("Gemini API error"))
        
        mock_neo4j = MockNeo4j.return_value
        mock_neo4j.mark_episode_ready = AsyncMock()
        
        result = await finalize_episode_with_vectors(
            episode_id="test_ep_003",
            user_id="test_user",
            session_id="test_session",
            summary="Valid summary for testing embedding failure scenario.",
            model="gemini-2.0-flash"
        )
        
        assert result["status"] == "partial"
        assert result["vector_status"] == "FAILED"
        assert "Embedding failed" in result["error"]
        
        # Verify Neo4j updated with FAILED status
        call_args = mock_neo4j.mark_episode_ready.call_args
        assert call_args.kwargs["vector_status"] == "FAILED"
        assert "Gemini API error" in call_args.kwargs["vector_error"]


@pytest.mark.asyncio
async def test_finalize_episode_qdrant_failure():
    """
    Qdrant upsert fails: Episode READY, vector_status=FAILED, embedding stored in Neo4j
    
    WHY: Graceful degradation - vector search unavailable, fallback to graph retrieval.
    """
    with patch('Atlas.memory.episode_pipeline.GeminiEmbedder') as MockEmbedder, \
         patch('Atlas.memory.episode_pipeline.QdrantManager') as MockQdrant, \
         patch('Atlas.memory.episode_pipeline.Neo4jManager') as MockNeo4j, \
         patch('Atlas.memory.episode_pipeline.BYPASS_VECTOR_SEARCH', False):
        
        # Embedding succeeds
        mock_embedder = MockEmbedder.return_value
        mock_embedder.embed = AsyncMock(return_value=[0.2] * 768)
        
        # Qdrant fails
        mock_qdrant = MockQdrant.return_value
        mock_qdrant.upsert_episode = AsyncMock(side_effect=ConnectionError("Qdrant unavailable"))
        
        mock_neo4j = MockNeo4j.return_value
        mock_neo4j.mark_episode_ready = AsyncMock()
        
        result = await finalize_episode_with_vectors(
            episode_id="test_ep_004",
            user_id="test_user",
            session_id="test_session",
            summary="Testing Qdrant failure with successful embedding generation.",
            model="gemini-2.0-flash"
        )
        
        assert result["status"] == "partial"
        assert result["vector_status"] == "FAILED"
        assert "Qdrant upsert failed" in result["error"]
        assert result["embedding_model"] == "models/text-embedding-004"  # Still recorded
        
        # Verify Neo4j got the embedding (backward compat)
        call_args = mock_neo4j.mark_episode_ready.call_args
        assert call_args.kwargs["embedding"] is not None
        assert len(call_args.kwargs["embedding"]) == 768
        assert call_args.kwargs["vector_status"] == "FAILED"


@pytest.mark.asyncio
async def test_finalize_episode_bypass_mode():
    """
    BYPASS_VECTOR_SEARCH=true: Skip all vector processing
    
    WHY: Feature flag for gradual rollout / emergency disable.
    """
    with patch('Atlas.memory.episode_pipeline.Neo4jManager') as MockNeo4j, \
         patch('Atlas.memory.episode_pipeline.BYPASS_VECTOR_SEARCH', True):
        
        mock_neo4j = MockNeo4j.return_value
        mock_neo4j.mark_episode_ready = AsyncMock()
        
        result = await finalize_episode_with_vectors(
            episode_id="test_ep_005",
            user_id="test_user",
            session_id="test_session",
            summary="Testing bypass mode with valid summary length.",
            model="gemini-2.0-flash"
        )
        
        assert result["status"] == "success"
        assert result["vector_status"] == "SKIPPED"
        assert "bypassed" in result["error"].lower()
        
        call_args = mock_neo4j.mark_episode_ready.call_args
        assert call_args.kwargs["vector_status"] == "SKIPPED"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_finalize_episode_integration_local():
    """
    Integration test with local Docker Qdrant (optional).
    
    WHY: End-to-end validation in realistic environment.
    
    REQUIRES:
    - Docker Qdrant running on localhost:6333
    - QDRANT_TEST_MODE=local
    - Neo4j connection (or mocked)
    """
    test_mode = os.getenv("QDRANT_TEST_MODE")
    if test_mode != "local":
        pytest.skip("Integration test requires QDRANT_TEST_MODE=local")
    
    # This would be a real integration test
    # For now, placeholder to show structure
    pytest.skip("Full integration test not implemented yet - structure only")


# Marker configuration for pytest
# Run with: pytest tests/test_episode_pipeline.py -v
# Run integration: pytest tests/test_episode_pipeline.py -m integration -v
