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
from datetime import datetime
from typing import Optional, List, Dict
import redis.asyncio as redis
from atlas.memory.gemini_embedder import GeminiEmbedder
from atlas.memory.text_normalize import normalize_text_for_dedupe

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
        from atlas.config import BYPASS_SEMANTIC_CACHE
        start_t = time.time()
        
        if BYPASS_SEMANTIC_CACHE or not self.client:
            return {"response": None, "similarity": 0.0, "latency_ms": 0}
        
        try:
            normalized_query = normalize_text_for_dedupe(query)
            query_emb = await self.embedder.embed(normalized_query)
            
            # Use SCAN to find candidate keys for THIS user
            match_pattern = f"cache:{user_id}:*"
            keys = []
            async for key in self.client.scan_iter(match=match_pattern, count=self.max_scan_keys):
                keys.append(key)
                if len(keys) >= self.max_scan_keys:
                    break
            
            best_match = None
            best_similarity = 0.0
            threshold = getattr(self, "similarity_threshold", 0.92)
            
            for key in keys:
                try:
                    raw_cached = await self.client.get(key)
                    if not raw_cached: continue
                    data = json.loads(raw_cached)
                    cached_emb = data.get("embedding", [])
                    if not cached_emb or len(cached_emb) != len(query_emb): continue
                    
                    similarity = self._cosine_similarity(query_emb, cached_emb)
                    if similarity >= threshold and similarity > best_similarity:
                        best_similarity = similarity
                        best_match = data.get("response")
                except: continue
                
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
        from atlas.config import BYPASS_SEMANTIC_CACHE
        if BYPASS_SEMANTIC_CACHE or not self.client:
            return False
        
        try:
            normalized = normalize_text_for_dedupe(query)
            query_emb = await self.embedder.embed(normalized)
            
            # Format: cache:{user_id}:{hash}
            query_hash = hashlib.md5(normalized.encode()).hexdigest()
            key = f"cache:{user_id}:{query_hash}"
            
            await self.client.setex(
                key,
                self.ttl,
                json.dumps({
                    "query": query[:500],
                    "embedding": query_emb,
                    "response": response,
                    "user_id": user_id,
                    "timestamp": datetime.utcnow().isoformat()
                })
            )
            return True
        except Exception as e:
            logger.error(f"Semantic cache set failed: {e}")
            return False

    async def clear_user(self, user_id: str) -> int:
        """Kullanıcıya ait tüm cache kayıtlarını temizler."""
        if not self.client:
            return 0
        try:
            match_pattern = f"cache:{user_id}:*"
            keys = []
            async for key in self.client.scan_iter(match=match_pattern):
                keys.append(key)
            
            if keys:
                await self.client.delete(*keys)
                logger.info(f"Semantic cache: {len(keys)} keys cleared for user {user_id}")
                return len(keys)
            return 0
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
