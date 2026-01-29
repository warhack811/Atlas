from typing import List, Dict
import logging
from Atlas.memory.graph_store.connector import GraphConnector

logger = logging.getLogger(__name__)

class GraphWriter:
    def __init__(self, connector: GraphConnector):
        self.connector = connector

    async def execute_write(self, cypher: str, params: Dict) -> int:
        session = await self.connector.get_session()
        async with session:
            try:
                result = await session.run(cypher, **params)
                summary = await result.consume()
                return summary.counters.nodes_created + summary.counters.relationships_created
            except Exception as e:
                logger.error(f"Neo4j write error: {e}")
                return 0
