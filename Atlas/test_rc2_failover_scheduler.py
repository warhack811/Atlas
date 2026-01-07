import unittest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from Atlas.scheduler import check_leader_election, _IS_LEADER, INSTANCE_ID

class TestRC2FailoverScheduler(unittest.IsolatedAsyncioTestCase):
    
    def setUp(self):
        # Global state'i resetle
        import Atlas.scheduler
        Atlas.scheduler._IS_LEADER = False

    @patch('Atlas.scheduler.neo4j_manager.try_acquire_lock', new_callable=AsyncMock)
    @patch('Atlas.scheduler.refresh_scheduler_jobs', new_callable=AsyncMock)
    async def test_promotion_to_leader(self, mock_refresh, mock_lock):
        """Kilidi alınca lider olduğunu doğrula."""
        mock_lock.return_value = True
        
        await check_leader_election()
        
        from Atlas.scheduler import _IS_LEADER
        self.assertTrue(_IS_LEADER)
        mock_refresh.assert_called_once()

    @patch('Atlas.scheduler.neo4j_manager.try_acquire_lock', new_callable=AsyncMock)
    async def test_demotion_from_leader(self, mock_lock):
        """Kilidi kaybedince follower olduğunu doğrula."""
        # Önce lider yap
        import Atlas.scheduler
        Atlas.scheduler._IS_LEADER = True
        
        # Kilidi kaybet
        mock_lock.return_value = False
        
        await check_leader_election()
        
        self.assertFalse(Atlas.scheduler._IS_LEADER)

    @patch('Atlas.scheduler.neo4j_manager.try_acquire_lock', new_callable=AsyncMock)
    @patch('Atlas.scheduler.scheduler')
    async def test_job_cleanup_on_demote(self, mock_sched, mock_lock):
        """Demote olduğunda lider işlerinin (obs, due, heartbeat) silindiğini doğrula."""
        import Atlas.scheduler
        Atlas.scheduler._IS_LEADER = True
        mock_lock.return_value = False
        
        # Mock jobs
        mock_job1 = MagicMock()
        mock_job1.id = "obs:u1"
        mock_job2 = MagicMock()
        mock_job2.id = "leader_election" # Bu silinmemeli
        
        mock_sched.get_jobs.return_value = [mock_job1, mock_job2]
        
        await check_leader_election()
        
        # obs:u1 silinmeli
        mock_sched.remove_job.assert_any_call("obs:u1")
        # leader_election silinmemeli
        calls = [c.args[0] for c in mock_sched.remove_job.call_args_list]
        self.assertNotIn("leader_election", calls)

if __name__ == "__main__":
    unittest.main()
