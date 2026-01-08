import unittest
import asyncio
from unittest.mock import patch, MagicMock
from Atlas.api import purge_test_data, PurgeTestDataRequest
from fastapi import HTTPException

class TestAdminPurgeTestData(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    @patch("Atlas.config.DEBUG", False)
    def test_purge_forbidden_if_not_debug(self):
        request = PurgeTestDataRequest(user_id_prefix="test_")
        with self.assertRaises(HTTPException) as cm:
            self.loop.run_until_complete(purge_test_data(request))
        self.assertEqual(cm.exception.status_code, 403)

    @patch("Atlas.config.DEBUG", True)
    @patch("Atlas.memory.neo4j_manager.neo4j_manager.query_graph")
    def test_purge_success(self, mock_query):
        mock_query.return_value = asyncio.Future()
        mock_query.return_value.set_result([])
        
        request = PurgeTestDataRequest(user_id_prefix="test_")
        result = self.loop.run_until_complete(purge_test_data(request))
        
        self.assertTrue(result["success"])
        self.assertIn("test_", result["message"])
        
        # Verify query matches prefix
        args, kwargs = mock_query.call_args
        self.assertIn("MATCH (u:User) WHERE u.id STARTS WITH $prefix", args[0])
        self.assertEqual(kwargs["params"]["prefix"], "test_")

if __name__ == "__main__":
    unittest.main()
