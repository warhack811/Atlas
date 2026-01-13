"""
ATLAS FAZ-Y - Gemini Embedding API Wrapper
-------------------------------------------
Metinleri 768-boyutlu vektörlere dönüştüren Gemini API entegrasyonu.
Batch processing ve rate limiting desteği ile free tier optimizasyonu.
"""

import httpx
import asyncio
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class GeminiEmbedder:
    """
    Low-memory cloud embedding using Gemini text-embedding-004 API
    
    Features:
    - 768-dimensional embeddings
    - Batch processing support
    - Rate limiting (60 RPM free tier)
    - Automatic retry on errors
    """
    
    MODEL = "models/text-embedding-004"
    DIMENSION = 768
    MAX_BATCH_SIZE = 100
    RPM_LIMIT = 60  # Free tier limit
    
    def __init__(self, api_base: Optional[str] = None):
        """
        Initialize Gemini Embedder
        
        Args:
            api_base: Optional API base URL override
        """
        from Atlas.config import API_CONFIG
        self.api_base = api_base or API_CONFIG.get(
            "gemini_api_base",
            "https://generativelanguage.googleapis.com/v1beta"
        )
    
    async def embed(self, text: str, retry_count: int = 3) -> List[float]:
        """
        Generate embedding for a single text
        
        Args:
            text: Input text to embed
            retry_count: Number of retries on failure
            
        Returns:
            768-dimensional embedding vector
        """
        # Handle empty input
        if not text or len(text.strip()) == 0:
            logger.warning("Empty text provided, returning zero vector")
            return [0.0] * self.DIMENSION
        
        # Get API key
        from Atlas.config import Config
        api_key = Config.get_random_gemini_key()
        
        if not api_key:
            logger.error("No Gemini API key available")
            raise ValueError("Gemini API key not configured")
        
        url = f"{self.api_base}/{self.MODEL}:embedContent"
        
        for attempt in range(retry_count):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        url,
                        params={"key": api_key},
                        json={
                            "content": {
                                "parts": [{"text": text[:10000]}]  # Limit text length
                            }
                        },
                        headers={"Content-Type": "application/json"}
                    )
                    response.raise_for_status()
                    data = response.json()
                    embedding = data.get("embedding", {}).get("values", [])
                    
                    if len(embedding) != self.DIMENSION:
                        raise ValueError(f"Expected {self.DIMENSION} dimensions, got {len(embedding)}")
                    
                    return embedding
                    
            except httpx.HTTPError as e:
                logger.warning(f"Gemini API error (attempt {attempt + 1}/{retry_count}): {e}")
                if attempt == retry_count - 1:
                    logger.error(f"Failed to get embedding after {retry_count} attempts")
                    raise
                await asyncio.sleep(1.0 * (attempt + 1))  # Exponential backoff
            except Exception as e:
                logger.error(f"Unexpected error during embedding: {e}")
                raise
    
    async def embed_batch(
        self, 
        texts: List[str], 
        delay: float = 1.0,
        show_progress: bool = False
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts with rate limiting
        
        Args:
            texts: List of texts to embed
            delay: Delay between batches (seconds)
            show_progress: Log progress
            
        Returns:
            List of 768-dimensional embedding vectors
        """
        results = []
        total_batches = (len(texts) + self.MAX_BATCH_SIZE - 1) // self.MAX_BATCH_SIZE
        
        for i in range(0, len(texts), self.MAX_BATCH_SIZE):
            batch = texts[i:i + self.MAX_BATCH_SIZE]
            batch_num = (i // self.MAX_BATCH_SIZE) + 1
            
            if show_progress:
                logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} texts)")
            
            # Process batch in parallel
            batch_results = await asyncio.gather(
                *[self.embed(t) for t in batch],
                return_exceptions=True
            )
            
            # Handle exceptions in batch
            for idx, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    logger.error(f"Failed to embed text at index {i + idx}: {result}")
                    results.append([0.0] * self.DIMENSION)  # Zero vector fallback
                else:
                    results.append(result)
            
            # Rate limiting: 60 RPM = 1 per second minimum
            if i + self.MAX_BATCH_SIZE < len(texts):
                await asyncio.sleep(delay)
        
        return results
    
    @staticmethod
    def cosine_similarity(v1: List[float], v2: List[float]) -> float:
        """
        Calculate cosine similarity between two vectors
        
        Args:
            v1: First vector
            v2: Second vector
            
        Returns:
            Similarity score (0-1)
        """
        import numpy as np
        v1_np = np.array(v1)
        v2_np = np.array(v2)
        
        norm1 = np.linalg.norm(v1_np)
        norm2 = np.linalg.norm(v2_np)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(np.dot(v1_np, v2_np) / (norm1 * norm2))
