from Atlas.tasks import BaseJob, JobConfig, register_job
from Atlas.memory.neo4j_manager import neo4j_manager
from typing import List, Dict, Any, Optional
import logging
import uuid
import socket

logger = logging.getLogger(__name__)

# Her instance için benzersiz bir ID (Leader seçimi için)
INSTANCE_ID = f"{socket.gethostname()}:{uuid.uuid4().hex[:6]}"

@register_job
class HeartbeatJob(BaseJob):
    """Neo4j Bağlantı Canlılığı (Heartbeat)."""
    name = "heartbeat"
    config = JobConfig(interval_minutes=9, jitter=30, is_leader_only=False) # Tüm instance'lar yapmalı

    async def run(self):
        try:
            await neo4j_manager.query_graph("RETURN 1 AS heartbeat")
            logger.info("Neo4j Kalp Atışı Sinyali gönderildi.")
        except Exception as e:
            logger.error(f"Kalp atışı başarısız: {e}")

@register_job
class LeaderElectionJob(BaseJob):
    """Distributed lock kontrolü ve lider seçimi."""
    name = "leader_election"
    config = JobConfig(interval_seconds=30, jitter=0, is_leader_only=False) # Tüm instance'lar yarışır

    async def run(self, scheduler_coordinator: Any = None):
        """
        Liderlik durumunu kontrol eder. 
        Not: scheduler_coordinator, scheduler.py'deki mantığı tetiklemek için kullanılacak.
        """
        is_leader_now = await neo4j_manager.try_acquire_lock("global_scheduler", INSTANCE_ID, 90)
        if scheduler_coordinator:
            await scheduler_coordinator.update_leadership(is_leader_now, INSTANCE_ID)
