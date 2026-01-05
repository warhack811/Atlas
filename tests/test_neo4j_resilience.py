import asyncio
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from sandbox_router.memory.neo4j_manager import Neo4jManager
from neo4j.exceptions import ServiceUnavailable

class TestNeo4jResilience(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Reset singleton for testing
        Neo4jManager._instance = None
        self.manager = Neo4jManager()

    @patch("sandbox_router.memory.neo4j_manager.AsyncGraphDatabase.driver")
    async def test_retry_logic_on_service_unavailable(self, mock_driver_factory):
        # Setup: First call to run fails, second succeeds
        mock_driver = MagicMock()
        mock_session = AsyncMock()
        
        # Mock session.run to fail once then succeed
        mock_session.run.side_effect = [
            ServiceUnavailable("Connection lost"),
            AsyncMock(data=AsyncMock(return_value=[{"heartbeat": 1}]))
        ]
        
        mock_driver.session.return_value.__aenter__.return_value = mock_session
        mock_driver_factory.return_value = mock_driver

        # Execute
        # Note: query_graph will call _connect if driver is not initialized, 
        # or it will use available driver. In our test, __init__ calls _connect.
        
        # Trigger query
        with patch.object(self.manager, '_connect') as mock_reconnect:
            # We need to simulate the driver being set
            self.manager._driver = mock_driver
            self.manager._initialized = True
            
            # This should trigger 1 retry
            result = await self.manager.query_graph("RETURN 1")
            
            # Verify: _connect should have been called again after failure
            mock_reconnect.assert_called()
            self.assertEqual(mock_session.run.call_count, 2)

    @patch("sandbox_router.memory.neo4j_manager.AsyncGraphDatabase.driver")
    async def test_max_retries_exhausted(self, mock_driver_factory):
        mock_driver = MagicMock()
        mock_session = AsyncMock()
        mock_session.run.side_effect = ServiceUnavailable("Persistent failure")
        
        mock_driver.session.return_value.__aenter__.return_value = mock_session
        mock_driver_factory.return_value = mock_driver
        
        self.manager._driver = mock_driver
        self.manager._initialized = True
        
        # Execute
        result = await self.manager.query_graph("RETURN 1")
        
        # Verify result is empty list on failure
        self.assertEqual(result, [])
        # Verify it tried 3 times (max_retries = 3)
        self.assertEqual(mock_session.run.call_count, 3)

if __name__ == "__main__":
    unittest.main()
