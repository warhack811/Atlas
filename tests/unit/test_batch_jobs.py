import sys
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import importlib

class TestBatchJobs(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Create mocks
        self.mock_neo4j_manager = AsyncMock()
        self.mock_observer = MagicMock()
        self.mock_observer.check_triggers = AsyncMock()
        self.mock_scan_due_tasks = AsyncMock()

        # Patch dependencies
        self.patcher = patch.dict(sys.modules, {
            "Atlas.memory.neo4j_manager": MagicMock(neo4j_manager=self.mock_neo4j_manager),
            "Atlas.observer": MagicMock(observer=self.mock_observer),
            "Atlas.memory.due_scanner": MagicMock(scan_due_tasks=self.mock_scan_due_tasks),
            # We don't need to mock Atlas.tasks if we import batch_jobs directly,
            # but batch_jobs imports from Atlas.tasks.
            # Real Atlas.tasks should be fine if available.
        })
        self.patcher.start()

        # Import the module under test
        # We need to make sure we import/reload it to pick up the mocked modules
        import Atlas.tasks.batch_jobs
        importlib.reload(Atlas.tasks.batch_jobs)
        self.batch_jobs = Atlas.tasks.batch_jobs

    async def asyncTearDown(self):
        self.patcher.stop()

    async def test_observer_batch_job(self):
        # Setup
        users = [{"id": "u1"}, {"id": "u2"}, {"id": "u3"}]
        self.mock_neo4j_manager.query_graph.return_value = users

        job = self.batch_jobs.ObserverBatchJob()
        await job.run()

        # Verify
        self.mock_neo4j_manager.query_graph.assert_called_once()
        self.assertEqual(self.mock_observer.check_triggers.call_count, 3)
        self.mock_observer.check_triggers.assert_any_call("u1")
        self.mock_observer.check_triggers.assert_any_call("u2")
        self.mock_observer.check_triggers.assert_any_call("u3")

    async def test_due_scanner_batch_job(self):
        # Setup
        users = [{"id": "u1"}, {"id": "u2"}]
        self.mock_neo4j_manager.query_graph.return_value = users

        job = self.batch_jobs.DueScannerBatchJob()
        await job.run()

        # Verify
        self.mock_neo4j_manager.query_graph.assert_called_once()
        self.assertEqual(self.mock_scan_due_tasks.call_count, 2)
        self.mock_scan_due_tasks.assert_any_call("u1")
        self.mock_scan_due_tasks.assert_any_call("u2")

if __name__ == "__main__":
    unittest.main()
