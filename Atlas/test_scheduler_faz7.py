import unittest
from unittest.mock import patch, AsyncMock, MagicMock
from Atlas.scheduler import start_scheduler, scheduler

class TestSchedulerFaz7(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Stop scheduler if it's running from other tests
        if scheduler.running:
            scheduler.shutdown()

    @patch('Atlas.memory.neo4j_manager.neo4j_manager.query_graph', new_callable=AsyncMock)
    @patch('apscheduler.schedulers.asyncio.AsyncIOScheduler.start')
    @patch('apscheduler.schedulers.asyncio.AsyncIOScheduler.add_job')
    async def test_start_scheduler_registers_jobs(self, mock_add_job, mock_start, mock_query):
        # Case: 2 active users
        mock_query.return_value = [{"id": "user1"}, {"id": "user2"}]
        
        await start_scheduler()
        
        # Verify scheduler started
        mock_start.assert_called_once()
        
        # Verify jobs added for each user (2 jobs per user = 4 total)
        self.assertEqual(mock_add_job.call_count, 4)
        
        # Check job IDs
        job_ids = [call.kwargs['id'] for call in mock_add_job.call_args_list]
        self.assertIn("obs:user1", job_ids)
        self.assertIn("due:user1", job_ids)
        self.assertIn("obs:user2", job_ids)
        self.assertIn("due:user2", job_ids)

if __name__ == "__main__":
    unittest.main()
