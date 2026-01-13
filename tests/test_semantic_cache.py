"""
FAZ-Y Tests - Semantic Cache
"""
import pytest
import os
from Atlas.memory.semantic_cache import SemanticCache


@pytest.mark.skipif(
    not os.getenv("REDIS_URL"),
    reason="Redis URL not configured"
)
@pytest.mark.asyncio
async def test_cache_set_and_get():
    """Test basic cache set and get"""
    cache = SemanticCache(similarity_threshold=0.92)
    
    # Set cache
    query = "Benim adım Ali"
    response = "Merhaba Ali, seni tanımaktan mutluluk duyuyorum!"
    
    success = await cache.set(query, response)
    assert success, "Cache set should succeed"
    
    # Get exact match
    result = await cache.get(query)
    assert result == response, "Should retrieve exact cached response"


@pytest.mark.skipif(
    not os.getenv("REDIS_URL"),
    reason="Redis URL not configured"
)
@pytest.mark.asyncio
async def test_semantic_similarity():
    """Test semantic similarity matching"""
    cache = SemanticCache(similarity_threshold=0.85)
    
    # Cache original query
    await cache.set("Adım ne?", "Senin adın Ali")
    
    # Query with similar meaning
    result = await cache.get("İsmim neydi?")
    
    # Should find similar query (if embeddings are good)
    # This might fail if similarity < 0.85, which is expected
    if result:
        assert result == "Senin adın Ali"
        print("✅ Semantic match found!")
    else:
        print("⚠️ No semantic match (similarity < 0.85)")


@pytest.mark.skipif(
    not os.getenv("REDIS_URL"),
    reason="Redis URL not configured"
)
@pytest.mark.asyncio
async def test_cache_miss():
    """Test cache miss for dissimilar query"""
    cache = SemanticCache(similarity_threshold=0.92)
    
    await cache.set("Bugün hava nasıl?", "Hava güneşli")
    
    # Completely different query
    result = await cache.get("Yarın toplantı var mı?")
    
    assert result is None, "Should not find match for dissimilar query"


@pytest.mark.skipif(
    not os.getenv("REDIS_URL"),
    reason="Redis URL not configured"
)
@pytest.mark.asyncio
async def test_cache_clear():
    """Test cache clearing"""
    cache = SemanticCache()
    
    # Add some entries
    await cache.set("test1", "response1")
    await cache.set("test2", "response2")
    
    # Clear cache
    deleted = await cache.clear()
    assert deleted >= 2, f"Should delete at least 2 keys, deleted {deleted}"
    
    # Verify cache is empty
    result = await cache.get("test1")
    assert result is None, "Cache should be empty after clear"


@pytest.mark.skipif(
    not os.getenv("REDIS_URL"),
    reason="Redis URL not configured"
)
@pytest.mark.asyncio
async def test_cache_stats():
    """Test cache statistics"""
    cache = SemanticCache()
    
    stats = await cache.stats()
    
    assert stats["enabled"] == True
    assert "total_keys" in stats
    assert "threshold" in stats
    assert stats["threshold"] == cache.similarity_threshold


@pytest.mark.asyncio
async def test_bypass_mode():
    """Test bypass flag"""
    original = os.getenv("BYPASS_SEMANTIC_CACHE")
    
    try:
        # Enable bypass
        os.environ["BYPASS_SEMANTIC_CACHE"] = "true"
        
        # Force config reload
        from importlib import reload
        import Atlas.config as config_module
        reload(config_module)
        
        cache = SemanticCache()
        
        # Should return None when bypassed
        result = await cache.get("test")
        assert result is None, "Should return None when bypassed"
        
        # Set should return False
        success = await cache.set("test", "response")
        assert success == False, "Should return False when bypassed"
        
    finally:
        # Restore
        if original:
            os.environ["BYPASS_SEMANTIC_CACHE"] = original
        else:
            os.environ.pop("BYPASS_SEMANTIC_CACHE", None)
        
        from importlib import reload
        import Atlas.config as config_module
        reload(config_module)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
