import asyncio
import logging
from neo4j import AsyncGraphDatabase
from Atlas.settings import settings

logger = logging.getLogger(__name__)

class GraphConnector:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GraphConnector, cls).__new__(cls)
            cls._instance._driver = None
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized: return
        self._connect()

    def _connect(self):
        try:
            if self._driver:
                asyncio.create_task(self._driver.close())

            self._driver = AsyncGraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
            )
            self._initialized = True
            logger.info(f"Neo4j connected: {settings.NEO4J_URI}")
        except Exception as e:
            self._initialized = False
            logger.error(f"Neo4j connection failed: {e}")

    async def get_session(self):
        if not self._driver or not self._initialized:
            self._connect()
        return self._driver.session()

    async def close(self):
        if self._driver:
            await self._driver.close()
