import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from Atlas.tasks import TaskRegistry
# Task modüllerini import ederek registry'e kayıt olmalarını sağla
import Atlas.tasks.maintenance
import Atlas.tasks.system
import Atlas.tasks.cognitive

from Atlas.memory.neo4j_manager import neo4j_manager
from Atlas.observer import observer
from Atlas.memory.due_scanner import scan_due_tasks

logger = logging.getLogger(__name__)

class SchedulerCoordinator:
    """Zamanlayıcıyı ve liderlik durumunu koordine eden merkezi yönetici."""
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.is_leader = False
        self.instance_id = None # system.py içindeki INSTANCE_ID ile senkronize olacak

    async def update_leadership(self, is_leader: bool, instance_id: str):
        """Liderlik durumunu günceller ve görevleri buna göre reorganize eder."""
        self.instance_id = instance_id
        old_leader_status = self.is_leader
        self.is_leader = is_leader
        
        if is_leader and not old_leader_status:
            await self._promote()
        elif not is_leader and old_leader_status:
            await self._demote()

    async def _promote(self):
        logger.info(f"Scheduler: {self.instance_id} LİDER olarak atandı!")
        await self.refresh_jobs()

    async def _demote(self):
        logger.warning(f"Scheduler: {self.instance_id} Liderliği KAYBETTİ.")
        # Sadece liderde çalışan işleri temizle
        for job in self.scheduler.get_jobs():
            # Check custom attribute if we can, or rely on naming
            if job.id.startswith("L:"):
                self.scheduler.remove_job(job.id)

    async def refresh_jobs(self):
        """Job'ları registry'den yükler ve senkronize eder."""
        # Static Jobs from Registry
        for job_cls in TaskRegistry.get_all_jobs():
            job_inst = job_cls()
            job_id = f"{'L' if job_inst.config.is_leader_only else 'F'}:{job_inst.name}"
            
            # Eğer sadece liderde çalışacaksa ve biz lider değilsek ekleme/kaldır
            if job_inst.config.is_leader_only and not self.is_leader:
                if self.scheduler.get_job(job_id):
                    self.scheduler.remove_job(job_id)
                continue
                
            trigger = IntervalTrigger(
                hours=job_inst.config.interval_hours or 0,
                minutes=job_inst.config.interval_minutes or 0,
                seconds=job_inst.config.interval_seconds or 0,
                jitter=job_inst.config.jitter
            )
            
            # Leader election job'a coordinator'ı pasla
            args = []
            if job_inst.name == "leader_election":
                args = [self]

            self.scheduler.add_job(
                job_inst.run,
                trigger=trigger,
                id=job_id,
                args=args,
                replace_existing=True
            )

        # Dynamic User Jobs (Sadece Liderse)
        if self.is_leader:
            await self.sync_user_jobs()

    async def sync_user_jobs(self):
        """Kullanıcı bazlı job'ları (observer, due_scanner) senkronize eder."""
        query = "MATCH (u:User) WHERE u.notifications_enabled = true RETURN u.id as id"
        try:
            results = await neo4j_manager.query_graph(query)
            active_uids = {res["id"] for res in results}
            
            current_job_ids = {j.id for j in self.scheduler.get_jobs()}
            
            for uid in active_uids:
                # Observer (15dk)
                obs_id = f"U:obs:{uid}"
                if obs_id not in current_job_ids:
                    self.scheduler.add_job(
                        observer.check_triggers,
                        trigger=IntervalTrigger(minutes=15, jitter=60),
                        args=[uid],
                        id=obs_id
                    )
                # Due Scanner (5dk)
                due_id = f"U:due:{uid}"
                if due_id not in current_job_ids:
                    self.scheduler.add_job(
                        scan_due_tasks,
                        trigger=IntervalTrigger(minutes=5, jitter=30),
                        args=[uid],
                        id=due_id
                    )
            
            # Cleanup inactive
            for jid in current_job_ids:
                if jid.startswith("U:"):
                    uid_part = jid.split(":")[-1]
                    if uid_part not in active_uids:
                        self.scheduler.remove_job(jid)
        except Exception as e:
            logger.error(f"User job sync error: {e}")

# Global Nesne
coordinator = SchedulerCoordinator()
scheduler = coordinator.scheduler # Geriye dönük uyumluluk için

async def start_scheduler():
    if coordinator.scheduler.running:
        return
    
    coordinator.scheduler.start()
    # İlk olarak tüm instance'larda çalışması gereken (Heartbeat, Leader Election) işleri yükle
    await coordinator.refresh_jobs()
    logger.info("Modular Scheduler başlatıldı.")

def stop_scheduler():
    if coordinator.scheduler.running:
        coordinator.scheduler.shutdown()
        logger.info("Scheduler durduruldu.")
