"""
Episode Embedding Pipeline - Orchestrator (Production-Hardened)

Finalizes episodes with vector embeddings:
1. Generate embedding (Gemini) with retry/backoff
2. Upsert to Qdrant with retry/backoff
3. Update Neo4j with metadata

WHY: Single responsibility module for episode finalization lifecycle.
     Graceful degradation on Qdrant failures.
     
RISK: Embedding generation adds latency (~500ms-2s per episode).
      Mitigated by: Background async processing in scheduler.
      
PERFORMANCE: Async throughout, optional wait parameter for Qdrant.

Y.4 HARDENING:
- Async retry/backoff for transient failures
- Dependency injection for testability
- Proper type hints (Dict[str, Any])
"""

import logging
import asyncio
import random
from typing import Optional, Dict, Any
from datetime import datetime

from Atlas.config import (
    BYPASS_VECTOR_SEARCH,
    STORE_EPISODE_EMBEDDING_IN_NEO4J,
    EPISODE_RETRY_MAX_ATTEMPTS,
    EPISODE_RETRY_BASE_DELAY,
    EPISODE_RETRY_JITTER
)
from Atlas.memory.gemini_embedder import GeminiEmbedder
from Atlas.memory.qdrant_manager import QdrantManager
from Atlas.memory.neo4j_manager import Neo4jManager

logger = logging.getLogger(__name__)


async def _retry_with_backoff(
    func,
    max_attempts: int,
    base_delay: float,
    jitter: float,
    operation_name: str
):
    """
    Generic async retry with exponential backoff + jitter.
    
    Args:
        func: Async callable to retry
        max_attempts: Maximum retry attempts
        base_delay: Base delay in seconds (doubles each retry)
        jitter: Random jitter to add (0-jitter seconds)
        operation_name: Operation name for logging
    
    Returns:
        Result from func
    
    Raises:
        Last exception if all attempts fail
    """
    last_exception = None
    
    for attempt in range(1, max_attempts + 1):
        try:
            return await func()
        except Exception as e:
            last_exception = e
            
            if attempt == max_attempts:
                logger.error(
                    f"{operation_name}: All {max_attempts} attempts failed. "
                    f"Last error: {e}"
                )
                raise
            
            # Exponential backoff with jitter
            delay = (base_delay * (2 ** (attempt - 1))) + random.uniform(0, jitter)
            logger.warning(
                f"{operation_name}: Attempt {attempt}/{max_attempts} failed: {e}. "
                f"Retrying in {delay:.2f}s..."
            )
            await asyncio.sleep(delay)
    
    raise last_exception  # Should never reach here


async def finalize_episode_with_vectors(
    episode_id: str,
    user_id: str,
    session_id: str,
    summary: str,
    model: str,
    *,
    wait_for_qdrant: bool = False,
    min_summary_length: int = 10,
    # Dependency injection for testability
    embedder: Optional[GeminiEmbedder] = None,
    qdrant_manager: Optional[QdrantManager] = None,
    neo4j_manager: Optional[Neo4jManager] = None,
    # Retry settings (override config if needed)
    max_attempts: Optional[int] = None,
    base_delay: Optional[float] = None,
    jitter: Optional[float] = None
) -> Dict[str, Any]:
    """
    Finalize episode with vector embeddings and metadata (production-hardened).
    
    Flow:
        1. Validate summary length
        2. Generate embedding (Gemini) with retry/backoff
        3. Upsert to Qdrant (with user_id filter) with retry/backoff
        4. Update Neo4j (status=READY + vector metadata)
    
    Args:
        episode_id: Unique episode identifier
        user_id: User identifier (for Qdrant filtering)
        session_id: Session identifier
        summary: Episode summary text
        model: Model used for summary generation
        wait_for_qdrant: If True, wait for Qdrant indexing (default: False)
        min_summary_length: Minimum summary length to process (default: 10)
        embedder: Optional GeminiEmbedder instance (for testing)
        qdrant_manager: Optional QdrantManager instance (for testing)
        neo4j_manager: Optional Neo4jManager instance (for testing)
        max_attempts: Override retry attempts (default: EPISODE_RETRY_MAX_ATTEMPTS)
        base_delay: Override base delay (default: EPISODE_RETRY_BASE_DELAY)
        jitter: Override jitter (default: EPISODE_RETRY_JITTER)
    
    Returns:
        {
            "status": "success" | "partial" | "failed",
            "vector_status": "READY" | "FAILED" | "SKIPPED",
            "embedding_model": str | None,
            "error": str | None
        }
    
    Raises:
        Exception: On critical Neo4j failures (episode state must be updated)
    
    WHY: Graceful degradation - episode can be READY even if vector processing fails.
         This allows system to continue functioning with graph-only retrieval.
    """
    # Dependency injection: Create instances if not provided
    if embedder is None:
        embedder = GeminiEmbedder()
    if qdrant_manager is None:
        qdrant_manager = QdrantManager()
    if neo4j_manager is None:
        neo4j_manager = Neo4jManager()
    
    # Retry settings
    _max_attempts = max_attempts or EPISODE_RETRY_MAX_ATTEMPTS
    _base_delay = base_delay or EPISODE_RETRY_BASE_DELAY
    _jitter = jitter or EPISODE_RETRY_JITTER
    
    result: Dict[str, Any] = {
        "status": "success",
        "vector_status": "SKIPPED",  # Will be updated to READY or FAILED
        "embedding_model": None,
        "error": None
    }
    
    embedding = None
    embedding_model = None
    vector_error = None
    
    try:
        # 1. Validate summary
        if not summary or len(summary.strip()) < min_summary_length:
            logger.info(
                f"Episode {episode_id}: Summary too short ({len(summary)} chars), "
                f"skipping vector processing"
            )
            result["vector_status"] = "SKIPPED"
            result["error"] = "Summary too short"
            
            await neo4j_manager.mark_episode_ready(
                episode_id=episode_id,
                summary=summary,
                model=model,
                embedding=None,
                embedding_model=None,
                vector_status="SKIPPED",
                vector_updated_at=datetime.utcnow().isoformat(),
                vector_error="Summary too short for embedding"
            )
            return result
        
        # 2. Check bypass flag
        if BYPASS_VECTOR_SEARCH:
            logger.debug(f"Episode {episode_id}: Vector search bypassed")
            result["vector_status"] = "SKIPPED"
            result["error"] = "Vector search bypassed"
            
            await neo4j_manager.mark_episode_ready(
                episode_id=episode_id,
                summary=summary,
                model=model,
                embedding=None,
                embedding_model=None,
                vector_status="SKIPPED",
                vector_updated_at=datetime.utcnow().isoformat(),
                vector_error="BYPASS_VECTOR_SEARCH enabled"
            )
            return result
        
        # 3. Generate embedding with retry/backoff
        logger.debug(f"Episode {episode_id}: Generating embedding...")
        
        async def _embed():
            return await embedder.embed(summary)
        
        try:
            embedding = await _retry_with_backoff(
                _embed,
                _max_attempts,
                _base_delay,
                _jitter,
                f"Episode {episode_id} embedding"
            )
            embedding_model = "models/text-embedding-004"
            logger.debug(
                f"Episode {episode_id}: Embedding generated "
                f"({len(embedding)} dimensions)"
            )
        except Exception as e:
            logger.error(
                f"Episode {episode_id}: Embedding generation failed after "
                f"{_max_attempts} attempts: {e}",
                exc_info=True
            )
            vector_error = f"Embedding failed: {str(e)[:200]}"
            result["vector_status"] = "FAILED"
            result["error"] = vector_error
            result["status"] = "partial"
            
            await neo4j_manager.mark_episode_ready(
                episode_id=episode_id,
                summary=summary,
                model=model,
                embedding=None,  # No embedding generated
                embedding_model=None,
                vector_status="FAILED",
                vector_updated_at=datetime.utcnow().isoformat(),
                vector_error=vector_error
            )
            return result
        
        # 4. Upsert to Qdrant with retry/backoff
        logger.debug(f"Episode {episode_id}: Upserting to Qdrant...")
        
        async def _upsert():
            success = await qdrant_manager.upsert_episode(
                episode_id=episode_id,
                embedding=embedding,
                user_id=user_id,
                session_id=session_id,
                text=summary,
                timestamp=datetime.utcnow().isoformat(),
                wait=wait_for_qdrant
            )
            if not success:
                raise RuntimeError("Qdrant upsert returned False")
            return success
        
        try:
            await _retry_with_backoff(
                _upsert,
                _max_attempts,
                _base_delay,
                _jitter,
                f"Episode {episode_id} Qdrant upsert"
            )
            logger.info(f"Episode {episode_id}: Qdrant upsert successful")
            
        except Exception as e:
            logger.warning(
                f"Episode {episode_id}: Qdrant upsert failed after "
                f"{_max_attempts} attempts (graceful degradation): {e}",
                exc_info=True
            )
            vector_error = f"Qdrant upsert failed: {str(e)[:200]}"
            result["vector_status"] = "FAILED"
            result["embedding_model"] = embedding_model
            result["error"] = vector_error
            result["status"] = "partial"
            
            # STORE_EPISODE_EMBEDDING flag: backward compat vs. Qdrant-only
            embedding_to_store = embedding if STORE_EPISODE_EMBEDDING_IN_NEO4J else None
            
            await neo4j_manager.mark_episode_ready(
                episode_id=episode_id,
                summary=summary,
                model=model,
                embedding=embedding_to_store,
                embedding_model=embedding_model,
                vector_status="FAILED",
                vector_updated_at=datetime.utcnow().isoformat(),
                vector_error=vector_error
            )
            return result
        
        # 5. Update Neo4j with SUCCESS
        logger.debug(f"Episode {episode_id}: Updating Neo4j...")
        
        # STORE_EPISODE_EMBEDDING flag: backward compat vs. Qdrant-only
        embedding_to_store = embedding if STORE_EPISODE_EMBEDDING_IN_NEO4J else None
        
        await neo4j_manager.mark_episode_ready(
            episode_id=episode_id,
            summary=summary,
            model=model,
            embedding=embedding_to_store,
            embedding_model=embedding_model,
            vector_status="READY",
            vector_updated_at=datetime.utcnow().isoformat(),
            vector_error=None
        )
        
        result["vector_status"] = "READY"
        result["embedding_model"] = embedding_model
        logger.info(
            f"Episode {episode_id}: Finalization complete "
            f"(vector_status=READY, model={embedding_model})"
        )
        
        return result
        
    except Exception as e:
        # Critical Neo4j failures should propagate
        logger.error(
            f"Episode {episode_id}: Critical finalization failure: {e}",
            exc_info=True
        )
        result["status"] = "failed"
        result["vector_status"] = "FAILED"
        result["error"] = str(e)[:200]
        raise
