import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch, ANY
from Atlas.tasks import TaskRegistry, BaseJob
from Atlas.scheduler import coordinator, SchedulerCoordinator

@pytest.mark.asyncio
async def test_task_registry_registration():
    """Tüm temel görevlerin registry'e kaydedildiğini doğrula."""
    jobs = TaskRegistry.get_all_jobs()
    job_names = [j.name for j in jobs]
    
    assert "maintenance" in job_names
    assert "heartbeat" in job_names
    assert "leader_election" in job_names
    assert "episode_worker" in job_names
    assert "consolidate" in job_names

@pytest.mark.asyncio
async def test_scheduler_refresh_jobs_loading():
    """Scheduler yenilendiğinde registry'den job'ların yüklendiğini doğrula."""
    test_coordinator = SchedulerCoordinator()
    # Mock apscheduler
    test_coordinator.scheduler = MagicMock()
    test_coordinator.scheduler.get_jobs.return_value = []
    
    # Lider değilken refresh yap
    test_coordinator.is_leader = False
    await test_coordinator.refresh_jobs()
    
    # Leader olmayan job'lar eklenmiş olmalı (Heartbeat, Leader Election vb.)
    # add_job çağrılarını kontrol et
    added_ids = []
    for call in test_coordinator.scheduler.add_job.call_args_list:
        if "id" in call.kwargs:
            added_ids.append(call.kwargs["id"])
        elif len(call.args) >= 3 and isinstance(call.args[2], str):
             # apscheduler signature check if positional
             pass
    
    assert "F:heartbeat" in added_ids
    assert "F:leader_election" in added_ids
    # Lider job'ları (L:episode_worker) eklenmemeli
    assert "L:episode_worker" not in added_ids

@pytest.mark.asyncio
async def test_leadership_promotion_demotion():
    """Liderlik değiştiğinde job'ların güncellendiğini doğrula."""
    test_coordinator = SchedulerCoordinator()
    test_coordinator.scheduler = MagicMock()
    
    # 1. Promote to Leader
    with patch.object(test_coordinator, "refresh_jobs", new_callable=AsyncMock) as mock_refresh:
        await test_coordinator.update_leadership(True, "test_inst")
        assert test_coordinator.is_leader == True
        mock_refresh.assert_called_once()
    
    # 2. Demote to Follower
    # Mock active jobs to remove
    mock_job = MagicMock()
    mock_job.id = "L:maintenance"
    test_coordinator.scheduler.get_jobs.return_value = [mock_job]
    
    await test_coordinator.update_leadership(False, "test_inst")
    assert test_coordinator.is_leader == False
    test_coordinator.scheduler.remove_job.assert_called_with("L:maintenance")

@pytest.mark.asyncio
async def test_leader_election_trigger():
    """LeaderElectionJob'ın coordinator'ı tetiklediğini doğrula."""
    from Atlas.tasks.system import LeaderElectionJob
    
    job = LeaderElectionJob()
    mock_coordinator = AsyncMock()
    
    with patch("Atlas.memory.neo4j_manager.neo4j_manager.try_acquire_lock", return_value=True):
        await job.run(scheduler_coordinator=mock_coordinator)
        mock_coordinator.update_leadership.assert_called_with(True, ANY)
