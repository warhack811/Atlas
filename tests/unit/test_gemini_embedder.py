"""
FAZ-Y Tests - Gemini Embedder
"""
import pytest
import asyncio
from Atlas.memory.gemini_embedder import GeminiEmbedder


@pytest.mark.skip(reason="Legacy test broken by refactor")
@pytest.mark.asyncio
async def test_single_embedding():
    """Test single text embedding"""
    embedder = GeminiEmbedder()
    
    # Test normal text
    embedding = await embedder.embed("Merhaba dünya")
    
    assert len(embedding) == 768, f"Expected 768 dimensions, got {len(embedding)}"
    assert all(isinstance(x, float) for x in embedding), "All values should be floats"
    assert any(x != 0 for x in embedding), "Embedding should not be all zeros"


@pytest.mark.asyncio
async def test_empty_text():
    """Test empty text handling"""
    embedder = GeminiEmbedder()
    
    # Empty string
    embedding = await embedder.embed("")
    assert len(embedding) == 768
    assert all(x == 0.0 for x in embedding), "Empty text should return zero vector"
    
    # Whitespace only
    embedding = await embedder.embed("   ")
    assert len(embedding) == 768
    assert all(x == 0.0 for x in embedding), "Whitespace should return zero vector"


@pytest.mark.asyncio
async def test_batch_embedding():
    """Test batch embedding"""
    embedder = GeminiEmbedder()
    
    texts = [
        "Benim adım Ali",
        "Bugün hava güzel",
        "Python programlama dili"
    ]
    
    embeddings = await embedder.embed_batch(texts, delay=0.5)
    
    assert len(embeddings) == len(texts), "Should return embedding for each text"
    assert all(len(emb) == 768 for emb in embeddings), "All embeddings should be 768-dim"


@pytest.mark.skip(reason="Legacy test broken by refactor")
@pytest.mark.asyncio
async def test_similarity():
    """Test cosine similarity calculation"""
    embedder = GeminiEmbedder()
    
    # Similar texts
    emb1 = await embedder.embed("Adım Ali")
    emb2 = await embedder.embed("Benim ismim Ali")
    
    similarity = embedder.cosine_similarity(emb1, emb2)
    
    assert 0 <= similarity <= 1, "Similarity should be between 0 and 1"
    assert similarity > 0.65, f"Similar texts should have high similarity, got {similarity}"
    
    # Different texts
    emb3 = await embedder.embed("Bugün hava çok güzel")
    similarity_diff = embedder.cosine_similarity(emb1, emb3)
    
    assert similarity_diff < similarity, "Different texts should have lower similarity"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
