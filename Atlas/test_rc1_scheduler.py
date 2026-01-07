import unittest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from Atlas.scheduler import start_scheduler, refresh_scheduler_jobs, scheduler, INSTANCE_ID

class TestRC1Scheduler(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Her testte scheduler'ı temizle
        if scheduler.running:
            scheduler.shutdown()
        # Yeni bir scheduler örneği oluşturmak yerine mevcutu temizle
        for job in scheduler.get_jobs():
            scheduler.remove_job(job.id)

    @patch('Atlas.scheduler.neo4j_manager.try_acquire_lock', new_callable=AsyncMock)
    async def test_start_scheduler_always_runs(self, mock_lock):
        """Scheduler her durumda (follower bile olsa) çalışmalı. (RC-2 Update)"""
        # Case 1: Lider kilidini alamazsa bile scheduler.running olmalı
        mock_lock.return_value = False
        await start_scheduler()
        self.assertTrue(scheduler.running)
        
        # Case 2: Lider kilidini alırsa
        mock_lock.return_value = True
        await start_scheduler() # Bu check_leader_election tetikler
        self.assertTrue(scheduler.running)

    @patch('Atlas.memory.neo4j_manager.Neo4jManager.query_graph', new_callable=AsyncMock)
    async def test_refresh_scheduler_jobs_sync(self, mock_query):
        # Mock active users
        mock_query.return_value = [{"id": "u1"}]
        
        import Atlas.scheduler
        Atlas.scheduler._IS_LEADER = True # Lider taklidi yap
        
        if not scheduler.running:
            scheduler.start()
            
        # Add a dummy job for u2 that should be removed
        scheduler.add_job(lambda x: x, trigger='interval', minutes=5, id="obs:u2", args=["u2"])
        
        await refresh_scheduler_jobs()
        
        # u1 jobs should be added
        self.assertIsNotNone(scheduler.get_job("obs:u1"))
        self.assertIsNotNone(scheduler.get_job("due:u1"))
        
        # u2 job should be removed
        self.assertIsNone(scheduler.get_job("obs:u2"))

if __name__ == "__main__":
    unittest.main()
