"""
ATLAS FAZ-Y - Qdrant Vector Database Manager
---------------------------------------------
Episode embeddings için Qdrant Cloud entegrasyonu.
Singleton pattern ile tek instance yönetimi.
"""

import os
import logging
import uuid
from typing import List, Dict, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue

logger = logging.getLogger(__name__)


class QdrantManager:
    """
    Singleton Qdrant client for episode embeddings
    
    Features:
    - Episode embedding upsert
    - User-filtered similarity search
    - Automatic collection creation
    - Health checks
    """
    
    _instance = None
    
    def __new__(cls):
        """Singleton pattern: Only one instance"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize singleton (lazy - don't load credentials yet)"""
        if self._initialized:
            return
        
        # Lazy initialization - credentials loaded on first use
        self.url = None
        self.api_key = None
        self.client = None
        self.collection_name = "episodes"
        self.semantic_collection_name = "semantic_cache"
        self.dimension = 768
        self._client_init_attempted = False
        self._initialized = True
    
    def _ensure_client(self) -> bool:
        """
        Lazy client initialization - called on first use.
        
        WHY: Credentials may not be available at import time.
             Test mode vs production mode requires different handling.
        
        RISK: Local mode without guards could expose production to unauthenticated Qdrant.
              Mitigated by: Multi-tier safety checks (PYTEST_CURRENT_TEST + explicit flag).
        
        PERFORMANCE: Minimal - initialization happens once per instance.
        """
        if self.client is not None:
            return True
        
        if self._client_init_attempted:
            return False
        
        self._client_init_attempted = True
        
        # Detect test mode with production-safe guards
        # 1. Explicit test mode flag (set by test framework)
        test_mode = os.getenv("QDRANT_TEST_MODE", "").lower()
        # 2. Pytest is running (PYTEST_CURRENT_TEST is set by pytest)
        is_pytest_running = "PYTEST_CURRENT_TEST" in os.environ
        # 3. Local mode requires BOTH conditions for safety
        is_local_mode = (test_mode == "local" and is_pytest_running)
        
        # Load credentials at runtime
        self.url = os.getenv("QDRANT_URL")
        self.api_key = os.getenv("QDRANT_API_KEY")
        
        # Local test mode: Docker Qdrant without authentication
        if is_local_mode:
            # Default to localhost if URL not set
            if not self.url:
                self.url = "http://localhost:6333"
            
            # Local Qdrant doesn't require API key
            logger.info(f"Local test mode: Connecting to {self.url} (no auth)")
            
            try:
                self.client = QdrantClient(url=self.url)
                self._ensure_collection()
                self._validate_client_api()  # CRITICAL: Check API compatibility
                logger.info(f"Qdrant client initialized (local mode): {self.url}")
                return True
            except Exception as e:
                logger.error(f"Failed to initialize local Qdrant client: {e}")
                return False
        
        # Production/Cloud mode: Require URL and API key
        if not self.url or not self.api_key:
            logger.warning("Qdrant credentials not configured (cloud/prod mode requires both URL and API key)")
            return False
        
        try:
            self.client = QdrantClient(url=self.url, api_key=self.api_key)
            self._ensure_collection()
            self._validate_client_api()  # CRITICAL: Check API compatibility
            logger.info(f"Qdrant client initialized (cloud mode): {self.url}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Qdrant client: {e}")
            return False
    
    def _validate_client_api(self):
        """Validate qdrant-client API compatibility."""
        if not self.client:
            return
        
        has_query_points = hasattr(self.client, 'query_points')
        has_search_points = hasattr(self.client, 'search_points')
        
        if not (has_query_points or has_search_points):
            raise RuntimeError(
                "Qdrant client API incompatibility!\\n"
                "Required: query_points or search_points method\\n"
                "Fix: pip install --upgrade 'qdrant-client>=1.7.0'"
            )
        
        api_method = 'query_points' if has_query_points else 'search_points'
        logger.debug(f"✅ Qdrant API validation: {api_method} available")
    
    def _ensure_collection(self):
        """Create collection if not exists (idempotent)"""
        if not self.client:
            return
        
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            
            if not exists:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.dimension,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Created Qdrant collection: {self.collection_name}")
            else:
                logger.info(f"Qdrant collection already exists: {self.collection_name}")

            # Ensure payload indexes for filtering (Critical for delete operations)
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="user_id",
                    field_schema="keyword"
                )
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="session_id",
                    field_schema="keyword"
                )
                logger.debug("Qdrant payload indexes ensured for user_id and session_id")
            except Exception as ie:
                logger.warning(f"Failed to ensure Qdrant payload indexes: {ie}")

            # Ensure semantic cache collection
            self._ensure_semantic_collection()

        except Exception as e:
            logger.error(f"Failed to ensure collection: {e}")
            raise

    def _ensure_semantic_collection(self):
        """Create semantic cache collection if not exists"""
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.semantic_collection_name for c in collections)

            if not exists:
                self.client.create_collection(
                    collection_name=self.semantic_collection_name,
                    vectors_config=VectorParams(
                        size=self.dimension,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Created Qdrant collection: {self.semantic_collection_name}")

            # Indexes for semantic cache
            try:
                self.client.create_payload_index(
                    collection_name=self.semantic_collection_name,
                    field_name="user_id",
                    field_schema="keyword"
                )
                self.client.create_payload_index(
                    collection_name=self.semantic_collection_name,
                    field_name="expiry",
                    field_schema="integer"
                )
                logger.debug("Qdrant payload indexes ensured for semantic cache")
            except Exception as ie:
                logger.warning(f"Failed to ensure semantic cache payload indexes: {ie}")

        except Exception as e:
            logger.error(f"Failed to ensure semantic collection: {e}")
            # Don't raise here to allow main app to continue if cache fails
    
    async def upsert_episode(
        self,
        episode_id: str,
        embedding: List[float],
        user_id: str,
        session_id: str,
        text: str,
        timestamp: str,
        *,
        wait: bool = True
    ) -> bool:
        """
        Insert or update episode embedding
        
        Args:
            episode_id: Unique episode identifier
            embedding: 768-dimensional vector
            user_id: User identifier for filtering
            session_id: Session identifier
            text: Original text (truncated to 1000 chars)
            timestamp: ISO format timestamp
            wait: If True, wait for operation to complete (strong consistency)
                  If False, return immediately after acknowledgment (eventual consistency)
            
        Returns:
            True if successful, False otherwise
        """
        # Check bypass flag
        from Atlas.config import BYPASS_VECTOR_SEARCH
        if BYPASS_VECTOR_SEARCH:
            logger.debug("Vector search bypassed")
            return False
        
        # Lazy client initialization
        if not self._ensure_client():
            logger.debug("Client not available")
            return False
        
        try:
            # Convert string episode_id to UUID (Qdrant requires int or UUID)
            # Use RFC 4122 uuid5 for deterministic, collision-safe UUID generation
            # NAMESPACE_DNS chosen as stable namespace for episode identifiers
            point_id = uuid.uuid5(uuid.NAMESPACE_DNS, episode_id)
            
            point = PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    "episode_id": episode_id,  # Original string ID for application use
                    "user_id": user_id,
                    "session_id": session_id,
                    "text": text[:1000],  # Limit payload size
                    "timestamp": timestamp
                }
            )
            
            # Try with wait parameter (qdrant-client >= 1.7.0)
            try:
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=[point],
                    wait=wait
                )
            except TypeError:
                # Fallback for older qdrant-client versions that don't support wait parameter
                logger.warning("qdrant-client version does not support 'wait' parameter, using default behavior")
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=[point]
                )
            
            logger.debug(f"Upserted episode to Qdrant: {episode_id} (wait={wait})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to upsert episode {episode_id}: {e}")
            return False
    
    async def vector_search(
        self,
        query_embedding: List[float],
        user_id: str,
        top_k: int = 10,
        score_threshold: float = 0.7
    ) -> List[Dict]:
        """
        Semantic search with user filter
        
        Args:
            query_embedding: 768-dimensional query vector
            user_id: User identifier (required filter)
            top_k: Maximum results to return
            score_threshold: Minimum similarity score (0-1)
            
        Returns:
            List of matching episodes with scores
        """
        # Check bypass flag
        from Atlas.config import BYPASS_VECTOR_SEARCH
        if BYPASS_VECTOR_SEARCH:
            logger.debug("Vector search bypassed")
            return []
        
        # Lazy client initialization
        if not self._ensure_client():
            logger.debug("Client not available")
            return []
        
        try:
            # Build filter (common to all APIs)
            user_filter = Filter(
                must=[
                    FieldCondition(
                        key="user_id",
                        match=MatchValue(value=user_id)
                    )
                ]
            )
            
            results_list = []
            
            # Use query_points (modern API for qdrant-client >= 1.8)
            if hasattr(self.client, 'query_points'):
                # query_points signature: collection_name, query, query_filter, limit, 
                #                         score_threshold, with_payload, with_vectors
                try:
                    response = self.client.query_points(
                        collection_name=self.collection_name,
                        query=query_embedding,
                        query_filter=user_filter,
                        limit=top_k,
                        score_threshold=score_threshold,  # Native threshold support
                        with_payload=True,
                        with_vectors=False
                    )
                    
                    # QueryResponse.points contains results
                    if hasattr(response, 'points'):
                        results_list = response.points
                        
                        # Diagnostic logging
                        if len(results_list) == 0:
                            logger.debug(
                                f"query_points returned 0 points for user_id={user_id}, "
                                f"threshold={score_threshold}"
                            )
                    else:
                        logger.warning(f"Unexpected query_points response: {type(response)}")
                        results_list = []
                        
                except Exception as e:
                    logger.error(f"query_points failed: {e}", exc_info=True)
                    raise  # Fail-fast
                    
            # Fallback: search_points (older API, qdrant-client >= 1.0)
            elif hasattr(self.client, 'search_points'):
                try:
                    search_results = self.client.search_points(
                        collection_name=self.collection_name,
                        query_vector=query_embedding,
                        query_filter=user_filter,
                        limit=top_k,
                        score_threshold=score_threshold  # search_points supports native threshold
                    )
                    
                    # search_points returns list directly
                    results_list = search_results if isinstance(search_results, list) else []
                    
                except Exception as e:
                    logger.error(f"search_points call failed: {e}", exc_info=True)
                    raise  # Fail-fast
                    
            # No compatible API found
            else:
                error_msg = (
                    "Qdrant client API incompatibility: No search method found!\n"
                    f"Available methods: {[m for m in dir(self.client) if 'search' in m.lower() or 'query' in m.lower()]}\n"
                    "Required: query_points or search_points\n"
                    "Fix: pip install --upgrade 'qdrant-client>=1.7.0'"
                )
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            
            # Map results to standard format
            return [
                {
                    "episode_id": r.payload.get("episode_id", str(r.id)),
                    "score": r.score,
                    "text": r.payload.get("text", ""),
                    "timestamp": r.payload.get("timestamp", ""),
                    "session_id": r.payload.get("session_id", ""),
                    "user_id": r.payload.get("user_id", "")
                }
                for r in results_list
            ]
            
        except RuntimeError:
            # Re-raise RuntimeError (fail-fast for API incompatibility)
            raise
        except Exception as e:
            logger.error(f"Vector search failed: {e}", exc_info=True)
            # Don't silently return [] - let tests fail on real errors
            raise
    
    async def delete_by_user(self, user_id: str) -> bool:
        """
        Delete all episodes for a user
        
        Args:
            user_id: User identifier
            
        Returns:
            True if successful
        """
        # Lazy client initialization
        if not self._ensure_client():
            return False
        
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="user_id",
                            match=MatchValue(value=user_id)
                        )
                    ]
                )
            )
            logger.info(f"Deleted all episodes for user: {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete episodes for user {user_id}: {e}")
            return False
    
    async def health_check(self) -> bool:
        """
        Check if Qdrant is accessible
        
        Returns:
            True if healthy
        """
        # Lazy client initialization
        if not self._ensure_client():
            return False
        
        try:
            self.client.get_collections()
            return True
        except Exception as e:
            logger.error(f"Qdrant health check failed: {e}")
            return False
    
    async def get_collection_info(self) -> Optional[Dict]:
        """
        Get collection statistics
        
        Returns:
            Collection info dict or None
        """
        # Lazy client initialization
        if not self._ensure_client():
            return None
        
        try:
            info = self.client.get_collection(self.collection_name)
            return {
                "name": info.config.params.vectors.size if hasattr(info.config.params, 'vectors') else self.collection_name,
                "vectors_count": info.points_count,
                "status": info.status.value
            }
        except Exception as e:
            logger.error(f"Failed to get collection info: {e}")
            return None

    async def upsert_cache(
        self,
        key: str,
        embedding: List[float],
        user_id: str,
        expiry: int,
        wait: bool = True
    ) -> bool:
        """
        Upsert cache entry
        """
        if not self._ensure_client():
            return False

        try:
            # Generate deterministic UUID from key
            point_id = uuid.uuid5(uuid.NAMESPACE_DNS, key)

            point = PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    "key": key,
                    "user_id": user_id,
                    "expiry": expiry
                }
            )

            try:
                self.client.upsert(
                    collection_name=self.semantic_collection_name,
                    points=[point],
                    wait=wait
                )
            except TypeError:
                 self.client.upsert(
                    collection_name=self.semantic_collection_name,
                    points=[point]
                )
            return True
        except Exception as e:
            logger.error(f"Failed to upsert cache: {e}")
            return False

    async def search_cache(
        self,
        query_embedding: List[float],
        user_id: str,
        score_threshold: float = 0.9,
        top_k: int = 1
    ) -> List[Dict]:
        """
        Search semantic cache
        """
        if not self._ensure_client():
            return []

        try:
            # Filter by user_id and expiry > now
            import time
            current_time = int(time.time())

            search_filter = Filter(
                must=[
                    FieldCondition(
                        key="user_id",
                        match=MatchValue(value=user_id)
                    ),
                    FieldCondition(
                        key="expiry",
                        range={"gt": current_time}
                    )
                ]
            )

            results = []
            if hasattr(self.client, 'query_points'):
                response = self.client.query_points(
                    collection_name=self.semantic_collection_name,
                    query=query_embedding,
                    query_filter=search_filter,
                    limit=top_k,
                    score_threshold=score_threshold,
                    with_payload=True
                )
                if hasattr(response, 'points'):
                    results = response.points
            elif hasattr(self.client, 'search_points'):
                results = self.client.search_points(
                    collection_name=self.semantic_collection_name,
                    query_vector=query_embedding,
                    query_filter=search_filter,
                    limit=top_k,
                    score_threshold=score_threshold
                )

            return [
                {
                    "key": r.payload.get("key"),
                    "score": r.score
                }
                for r in results
            ]
        except Exception as e:
            logger.error(f"Cache search failed: {e}")
            return []

    async def delete_cache_for_user(self, user_id: str) -> bool:
        """Delete cache entries for user"""
        if not self._ensure_client():
            return False

        try:
            self.client.delete(
                collection_name=self.semantic_collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="user_id",
                            match=MatchValue(value=user_id)
                        )
                    ]
                )
            )
            return True
        except Exception as e:
            logger.error(f"Failed to delete cache for user {user_id}: {e}")
            return False


# Singleton instance
qdrant_manager = QdrantManager()
