"""
ATLAS FAZ-Y - Redis Semantic Cache
-----------------------------------
Query-response çiftlerini embedding-based similarity ile cache'ler.
Benzer sorular için LLM çağrısını azaltır.
"""

import os
import json
import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Optional, List, Dict
import redis.asyncio as redis
from Atlas.memory.gemini_embedder import GeminiEmbedder
from Atlas.memory.text_normalize import normalize_text_for_dedupe

logger = logging.getLogger(__name__)


class SemanticCache:
    """
    Redis-based semantic cache for query-response pairs
    
    Features:
    - Embedding-based similarity matching
    - Configurable similarity threshold
    - TTL support (default 1 hour)
    - Bypass flag for gradual rollout
    - User isolation
    """
    
    def __init__(self, similarity_threshold: float = 0.92, ttl: int = 3600):
        """
        Initialize Semantic Cache
        """
        redis_url = os.getenv("REDIS_URL")
        
        if not redis_url:
            logger.warning("Redis URL not configured. Semantic cache will be disabled.")
            self.client = None
        else:
            try:
                self.client = redis.from_url(redis_url, decode_responses=True)
                logger.info("Redis client initialized for semantic cache")
            except Exception as e:
                logger.error(f"Failed to initialize Redis client: {e}")
                self.client = None
        
        self.embedder = GeminiEmbedder()
        self.similarity_threshold = similarity_threshold
        self.ttl = ttl
        self.max_scan_keys = 100  # Performance limit
    
    async def get(self, user_id: str, query: str) -> Optional[str]:
        """Backward compatible get() using get_with_meta()."""
        res = await self.get_with_meta(user_id, query)
        return res.get("response")

    async def get_with_meta(self, user_id: str, query: str) -> dict:
        """
        Production-grade retrieval with telemetry and user isolation.
        Returns: {"response": str|None, "similarity": float, "latency_ms": int}
        """
        from Atlas.config import BYPASS_SEMANTIC_CACHE
        from Atlas.memory.qdrant_manager import qdrant_manager

        start_t = time.time()
        
        if BYPASS_SEMANTIC_CACHE or not self.client:
            return {"response": None, "similarity": 0.0, "latency_ms": 0}
        
        try:
            normalized_query = normalize_text_for_dedupe(query)
            query_emb = await self.embedder.embed(normalized_query)
            threshold = getattr(self, "similarity_threshold", 0.92)
            
            # Use Vector Search (Qdrant) instead of SCAN
            results = await qdrant_manager.search_cache(
                query_embedding=query_emb,
                user_id=user_id,
                score_threshold=threshold,
                top_k=1
            )
            
            best_match = None
            best_similarity = 0.0
            
            if results:
                result = results[0]
                key = result.get("key")
                best_similarity = result.get("score", 0.0)

                # Fetch full response from Redis
                if key:
                    raw_cached = await self.client.get(key)
                    if raw_cached:
                        data = json.loads(raw_cached)
                        best_match = data.get("response")

            latency = int((time.time() - start_t) * 1000)
            if best_match:
                logger.info(f"CACHE HIT (user={user_id}): sim={best_similarity:.3f}")
            
            return {
                "response": best_match,
                "similarity": best_similarity,
                "latency_ms": latency
            }
        except Exception as e:
            logger.error(f"Semantic cache get_with_meta failed: {e}")
            return {"response": None, "similarity": 0.0, "latency_ms": int((time.time() - start_t) * 1000)}
    
    async def set(self, user_id: str, query: str, response: str) -> bool:
        """
        Caches a query-response pair with user isolation and TTL.
        """
        from Atlas.config import BYPASS_SEMANTIC_CACHE
        from Atlas.memory.qdrant_manager import qdrant_manager

        if BYPASS_SEMANTIC_CACHE or not self.client:
            return False
        
        try:
            normalized = normalize_text_for_dedupe(query)
            query_emb = await self.embedder.embed(normalized)
            
            # Format: cache:{user_id}:{hash}
            query_hash = hashlib.md5(normalized.encode()).hexdigest()
            key = f"cache:{user_id}:{query_hash}"
            
            # Store in Redis with TTL
            await self.client.setex(
                key,
                self.ttl,
                json.dumps({
                    "query": query[:500],
                    "embedding": query_emb, # Optional: keep embedding in Redis as backup/verification
                    "response": response,
                    "user_id": user_id,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            )

            # Upsert to Qdrant for vector search
            import time
            expiry = int(time.time()) + self.ttl
            await qdrant_manager.upsert_cache(
                key=key,
                embedding=query_emb,
                user_id=user_id,
                expiry=expiry
            )

            return True
        except Exception as e:
            logger.error(f"Semantic cache set failed: {e}")
            return False

    async def clear_user(self, user_id: str) -> int:
        """Kullanıcıya ait tüm cache kayıtlarını temizler."""
        from Atlas.memory.qdrant_manager import qdrant_manager

        if not self.client:
            return 0
        try:
            # Clear from Redis
            match_pattern = f"cache:{user_id}:*"
            keys = []
            async for key in self.client.scan_iter(match=match_pattern):
                keys.append(key)
            
            count = 0
            if keys:
                await self.client.delete(*keys)
                count = len(keys)

            # Clear from Qdrant
            await qdrant_manager.delete_cache_for_user(user_id)

            if count > 0:
                logger.info(f"Semantic cache: {count} keys cleared for user {user_id}")
            return count
        except Exception as e:
            logger.error(f"Semantic cache clear_user failed: {e}")
            return 0

    @staticmethod
    def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
        import numpy as np
        v1_np = np.array(v1)
        v2_np = np.array(v2)
        norm1 = np.linalg.norm(v1_np)
        norm2 = np.linalg.norm(v2_np)
        if norm1 == 0 or norm2 == 0: return 0.0
        return float(np.dot(v1_np, v2_np) / (norm1 * norm2))

# Singleton instance
semantic_cache = SemanticCache()
