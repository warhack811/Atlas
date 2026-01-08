import unittest
from unittest.mock import patch, AsyncMock, MagicMock
from Atlas.scheduler import sync_scheduler_jobs, scheduler

class TestRC1SchedulerRefresh(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Ensure scheduler is "running" for sync to work
        if not scheduler.running:
            scheduler.start()
        # Clean jobs
        for job in scheduler.get_jobs():
            scheduler.remove_job(job.id)
            
        import Atlas.scheduler
        Atlas.scheduler._IS_LEADER = True

    @patch('Atlas.memory.neo4j_manager.Neo4jManager.query_graph', new_callable=AsyncMock)
    async def test_sync_adds_new_jobs(self, mock_query):
        # Mock 1 active user
        mock_query.return_value = [{"id": "u1"}]
        
        await sync_scheduler_jobs()
        
        self.assertIsNotNone(scheduler.get_job("obs:u1"))
        self.assertIsNotNone(scheduler.get_job("due:u1"))

    @patch('Atlas.memory.neo4j_manager.Neo4jManager.query_graph', new_callable=AsyncMock)
    async def test_sync_removes_inactive_jobs(self, mock_query):
        # u2 is NOT in the mock results
        mock_query.return_value = [{"id": "u1"}]
        
        # Manually add a job for u2
        scheduler.add_job(lambda: None, trigger='interval', minutes=15, id="obs:u2")
        self.assertIsNotNone(scheduler.get_job("obs:u2"))
        
        await sync_scheduler_jobs()
        
        # u2 should be removed, u1 added
        self.assertIsNone(scheduler.get_job("obs:u2"))
        self.assertIsNotNone(scheduler.get_job("obs:u1"))

    async def asyncTearDown(self):
        if scheduler.running:
            scheduler.shutdown(wait=False)

if __name__ == "__main__":
    unittest.main()
