from atlas.tasks import BaseJob, JobConfig, register_job
from atlas.memory.neo4j_manager import neo4j_manager
from atlas.config import RETENTION_SETTINGS, MEMORY_CONFIDENCE_SETTINGS
import logging

logger = logging.getLogger(__name__)

@register_job
class MaintenanceJob(BaseJob):
    """Veri temizliği (Pruning) yapan periyodik görev."""
    name = "maintenance"
    config = JobConfig(interval_hours=24, jitter=300, is_leader_only=True)

    async def run(self):
        logger.info("Maintenance Job: Temizlik başlatıldı...")
        r = RETENTION_SETTINGS
        await neo4j_manager.prune_turns(r["TURN_RETENTION_DAYS"], r["MAX_TURNS_PER_SESSION"])
        await neo4j_manager.prune_episodes(r["EPISODE_RETENTION_DAYS"])
        await neo4j_manager.prune_notifications(r["NOTIFICATION_RETENTION_DAYS"])
        await neo4j_manager.prune_tasks(r["DONE_TASK_RETENTION_DAYS"])
        
        # FAZ-Y.5: Memory Pruning
        await neo4j_manager.prune_low_importance_memory(importance_threshold=0.4, age_days=30)
        # V4.3: Emotional Continuity TTL
        await neo4j_manager.archive_expired_moods(days=3)
        logger.info("Maintenance Job: Temizlik tamamlandı.")

@register_job
class DecayJob(BaseJob):
    """Soft signal confidence decay (RC-11)."""
    name = "decay_worker"
    config = JobConfig(interval_hours=24, jitter=600, is_leader_only=False) # Herkes yapabilir veya leader only seçilebilir

    async def run(self):
        rate = MEMORY_CONFIDENCE_SETTINGS.get("DECAY_RATE_PER_DAY", 0.05)
        logger.info(f"Decay Job: %{rate*100} oranında decay uygulanıyor...")
        await neo4j_manager.decay_soft_signals(rate)
