from typing import List, Dict, Optional
import logging
from neo4j.exceptions import ServiceUnavailable, SessionExpired
from Atlas.memory.graph_store.connector import GraphConnector

logger = logging.getLogger(__name__)

class GraphReader:
    def __init__(self, connector: GraphConnector):
        self.connector = connector

    async def query(self, cypher: str, params: Optional[Dict] = None) -> List[Dict]:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                session = await self.connector.get_session()
                async with session:
                    result = await session.run(cypher, **(params or {}))
                    return await result.data()
            except (ServiceUnavailable, SessionExpired) as e:
                logger.warning(f"Neo4j query retry ({attempt+1}): {e}")
                self.connector._connect()
            except Exception as e:
                logger.error(f"Neo4j query error: {e}")
                return []
        return []

    async def get_recent_turns(self, user_id: str, session_id: str, limit: int = 12) -> List[Dict]:
        query = """
        MATCH (s:Session {id: $sid})-[:HAS_TURN]->(t:Turn)
        WHERE s.user_id = $uid OR $uid IS NULL
        RETURN t.role as role, t.content as content, t.turn_index as turn_index
        ORDER BY t.turn_index DESC
        LIMIT $limit
        """
        return await self.query(query, {"uid": user_id, "sid": session_id, "limit": limit})
