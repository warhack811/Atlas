import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json
import os
import sys

# Set dummy env vars before importing
os.environ["REDIS_URL"] = "redis://localhost:6379"
os.environ["GEMINI_API_KEY"] = "dummy"

# Mock dependencies that might be missing in environment
neo4j = MagicMock()
sys.modules["neo4j"] = neo4j
sys.modules["neo4j.exceptions"] = MagicMock()
sys.modules["google.generativeai"] = MagicMock()

from Atlas.memory.semantic_cache import SemanticCache

@pytest.fixture
def mock_redis():
    mock_client = AsyncMock()
    # Mock Redis get/setex/delete
    mock_client.get.return_value = None
    mock_client.setex.return_value = True
    mock_client.delete.return_value = 1

    # Mock scan_iter
    async def async_iter(*args, **kwargs):
        yield "key1"
        yield "key2"
    mock_client.scan_iter = MagicMock(return_value=async_iter())

    # We need to patch where SemanticCache imports redis
    with patch("Atlas.memory.semantic_cache.redis.from_url", return_value=mock_client):
        yield mock_client

@pytest.fixture
def mock_qdrant():
    mock_qm = AsyncMock()
    mock_qm.search_cache.return_value = []
    mock_qm.upsert_cache.return_value = True
    mock_qm.delete_cache_for_user.return_value = True

    # Patch the instance in the module where it is defined
    with patch("Atlas.memory.qdrant_manager.qdrant_manager", mock_qm):
        yield mock_qm

@pytest.fixture
def mock_embedder():
    mock_emb = AsyncMock()
    mock_emb.embed.return_value = [0.1] * 768

    with patch("Atlas.memory.semantic_cache.GeminiEmbedder", return_value=mock_emb):
        yield mock_emb

@pytest.mark.asyncio
async def test_set_cache(mock_redis, mock_qdrant, mock_embedder):
    # SemanticCache might be instantiated at module level in Atlas.memory.semantic_cache
    # So we need to ensure we are testing a fresh instance or the global one with replaced client.

    # Reload module to ensure fresh instantiation with mocked redis.from_url
    # But wait, mock_redis fixture patches redis.from_url.
    # If we reload here, it should pick it up.

    import Atlas.memory.semantic_cache
    from importlib import reload
    reload(Atlas.memory.semantic_cache)

    from Atlas.memory.semantic_cache import SemanticCache

    # If SemanticCache is a class, we instantiate it.
    # If it's used as a singleton `semantic_cache` object, we need to access that.
    # Looking at the code, it seems to be a class.

    cache = SemanticCache()

    # Ensure client is our mock. Even if we reloaded, the patch should be active.
    # But to be absolutely safe against module level instantiation:
    cache.client = mock_redis
    cache.embedder = mock_embedder

    await cache.set("user1", "query", "response")

    # Verify Redis setex called
    mock_redis.setex.assert_called_once()

    # Verify Qdrant upsert called
    mock_qdrant.upsert_cache.assert_called_once()
    # Check arguments
    # upsert_cache(key=..., embedding=..., user_id=..., expiry=...)
    call_kwargs = mock_qdrant.upsert_cache.call_args.kwargs
    assert call_kwargs["user_id"] == "user1"
    assert "expiry" in call_kwargs
    assert "key" in call_kwargs

@pytest.mark.asyncio
async def test_get_cache_hit(mock_redis, mock_qdrant, mock_embedder):
    cache = SemanticCache()
    cache.client = mock_redis
    cache.embedder = mock_embedder

    # Mock Qdrant finding a match
    mock_qdrant.search_cache.return_value = [{"key": "cache:user1:hash", "score": 0.95}]

    # Mock Redis returning data
    mock_redis.get.return_value = json.dumps({
        "response": "cached_response",
        "embedding": [0.1]*768
    })

    # Note: SemanticCache.get calls get_with_meta
    result = await cache.get("user1", "query")

    assert result == "cached_response"
    mock_qdrant.search_cache.assert_called_once()
    mock_redis.get.assert_called_with("cache:user1:hash")

@pytest.mark.asyncio
async def test_get_cache_miss_no_vector_match(mock_redis, mock_qdrant, mock_embedder):
    cache = SemanticCache()
    cache.client = mock_redis
    cache.embedder = mock_embedder

    # Mock Qdrant finding NO match
    mock_qdrant.search_cache.return_value = []

    result = await cache.get("user1", "query")

    assert result is None
    mock_redis.get.assert_not_called()

@pytest.mark.asyncio
async def test_get_cache_miss_redis_expired(mock_redis, mock_qdrant, mock_embedder):
    cache = SemanticCache()
    cache.client = mock_redis
    cache.embedder = mock_embedder

    # Mock Qdrant finding a match
    mock_qdrant.search_cache.return_value = [{"key": "cache:user1:hash", "score": 0.95}]

    # Mock Redis returning None (expired)
    mock_redis.get.return_value = None

    result = await cache.get("user1", "query")

    assert result is None
    mock_redis.get.assert_called_with("cache:user1:hash")

@pytest.mark.asyncio
async def test_clear_user(mock_redis, mock_qdrant):
    cache = SemanticCache()
    cache.client = mock_redis

    await cache.clear_user("user1")

    # Verify Redis scan and delete
    mock_redis.delete.assert_called()

    # Verify Qdrant delete
    mock_qdrant.delete_cache_for_user.assert_called_with("user1")
