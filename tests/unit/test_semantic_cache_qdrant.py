import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json
import os
import sys
import importlib

# Ensure we don't pollute global sys.modules with mocks
# We will use patch.dict inside a fixture if we needed to mock modules globally,
# but here we can rely on installed dependencies or mock locally.

@pytest.fixture
def semantic_cache_class():
    # Set dummy env vars
    os.environ["REDIS_URL"] = "redis://localhost:6379"
    os.environ["GEMINI_API_KEY"] = "dummy"

    # If we need to mock neo4j or others, we should do it via patch.dict
    modules_to_patch = {
        "neo4j": MagicMock(),
        "neo4j.exceptions": MagicMock(),
        "google.generativeai": MagicMock()
    }

    # We only patch if they are NOT in sys.modules, or if we want to force mock.
    # But since we have dependencies installed, maybe we don't need to mock neo4j module?
    # However, if SemanticCache imports it, and we want to avoid real connection...
    # SemanticCache imports redis.

    with patch.dict(sys.modules, modules_to_patch):
        if "Atlas.memory.semantic_cache" in sys.modules:
            importlib.reload(sys.modules["Atlas.memory.semantic_cache"])
        else:
            importlib.import_module("Atlas.memory.semantic_cache")

        yield sys.modules["Atlas.memory.semantic_cache"].SemanticCache

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

    with patch("Atlas.memory.semantic_cache.redis.from_url", return_value=mock_client):
        yield mock_client

@pytest.fixture
def mock_qdrant():
    mock_qm = AsyncMock()
    mock_qm.search_cache.return_value = []
    mock_qm.upsert_cache.return_value = True
    mock_qm.delete_cache_for_user.return_value = True

    # Patch the instance in the module where it is defined
    # We need to patch it in the reloaded module!
    # But the module is reloaded inside semantic_cache_class fixture.
    # So we should patch it on the sys.modules['Atlas.memory.semantic_cache'] if possible,
    # OR simpler: patch Atlas.memory.qdrant_manager.qdrant_manager

    with patch("Atlas.memory.qdrant_manager.qdrant_manager", mock_qm):
        yield mock_qm

@pytest.fixture
def mock_embedder():
    mock_emb = AsyncMock()
    mock_emb.embed.return_value = [0.1] * 768

    with patch("Atlas.memory.semantic_cache.GeminiEmbedder", return_value=mock_emb):
        yield mock_emb

@pytest.mark.asyncio
async def test_set_cache(semantic_cache_class, mock_redis, mock_qdrant, mock_embedder):
    cache = semantic_cache_class()
    cache.client = mock_redis
    cache.embedder = mock_embedder

    with patch("Atlas.config.BYPASS_SEMANTIC_CACHE", False):
        await cache.set("user1", "query", "response")

    # Verify Redis setex called
    mock_redis.setex.assert_called_once()

    # Verify Qdrant upsert called
    mock_qdrant.upsert_cache.assert_called_once()
    # Check arguments
    call_kwargs = mock_qdrant.upsert_cache.call_args.kwargs
    assert call_kwargs["user_id"] == "user1"
    assert "expiry" in call_kwargs
    assert "key" in call_kwargs

@pytest.mark.asyncio
async def test_get_cache_hit(semantic_cache_class, mock_redis, mock_qdrant, mock_embedder):
    cache = semantic_cache_class()
    cache.client = mock_redis
    cache.embedder = mock_embedder

    # Mock Qdrant finding a match
    mock_qdrant.search_cache.return_value = [{"key": "cache:user1:hash", "score": 0.95}]

    # Mock Redis returning data
    mock_redis.get.return_value = json.dumps({
        "response": "cached_response",
        "embedding": [0.1]*768
    })

    with patch("Atlas.config.BYPASS_SEMANTIC_CACHE", False):
        result = await cache.get("user1", "query")

    assert result == "cached_response"
    mock_qdrant.search_cache.assert_called_once()
    mock_redis.get.assert_called_with("cache:user1:hash")

@pytest.mark.asyncio
async def test_get_cache_miss_no_vector_match(semantic_cache_class, mock_redis, mock_qdrant, mock_embedder):
    cache = semantic_cache_class()
    cache.client = mock_redis
    cache.embedder = mock_embedder

    # Mock Qdrant finding NO match
    mock_qdrant.search_cache.return_value = []

    with patch("Atlas.config.BYPASS_SEMANTIC_CACHE", False):
        result = await cache.get("user1", "query")

    assert result is None
    mock_redis.get.assert_not_called()

@pytest.mark.asyncio
async def test_get_cache_miss_redis_expired(semantic_cache_class, mock_redis, mock_qdrant, mock_embedder):
    cache = semantic_cache_class()
    cache.client = mock_redis
    cache.embedder = mock_embedder

    # Mock Qdrant finding a match
    mock_qdrant.search_cache.return_value = [{"key": "cache:user1:hash", "score": 0.95}]

    # Mock Redis returning None (expired)
    mock_redis.get.return_value = None

    with patch("Atlas.config.BYPASS_SEMANTIC_CACHE", False):
        result = await cache.get("user1", "query")

    assert result is None
    mock_redis.get.assert_called_with("cache:user1:hash")

@pytest.mark.asyncio
async def test_clear_user(semantic_cache_class, mock_redis, mock_qdrant):
    cache = semantic_cache_class()
    cache.client = mock_redis

    await cache.clear_user("user1")

    # Verify Redis scan and delete
    mock_redis.delete.assert_called()

    # Verify Qdrant delete
    mock_qdrant.delete_cache_for_user.assert_called_with("user1")
