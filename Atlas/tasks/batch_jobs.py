from Atlas.tasks import BaseJob, JobConfig, register_job
from Atlas.memory.neo4j_manager import neo4j_manager
from Atlas.observer import observer
from Atlas.memory.due_scanner import scan_due_tasks
import logging
import asyncio

logger = logging.getLogger(__name__)

@register_job
class ObserverBatchJob(BaseJob):
    name = "observer_batch_job"
    config = JobConfig(interval_minutes=15, jitter=60, is_leader_only=True)

    async def run(self):
        query = "MATCH (u:User) WHERE u.notifications_enabled = true RETURN u.id as id"
        try:
            results = await neo4j_manager.query_graph(query)
            active_uids = [res["id"] for res in results]

            if not active_uids:
                return

            logger.info(f"ObserverBatchJob: Processing {len(active_uids)} users.")

            sem = asyncio.Semaphore(10) # Limit concurrency

            async def safe_process(uid):
                async with sem:
                    try:
                        await observer.check_triggers(uid)
                    except Exception as e:
                        logger.error(f"ObserverBatchJob error for user {uid}: {e}")

            await asyncio.gather(*(safe_process(uid) for uid in active_uids))

        except Exception as e:
            logger.error(f"ObserverBatchJob failed: {e}")

@register_job
class DueScannerBatchJob(BaseJob):
    name = "due_scanner_batch_job"
    config = JobConfig(interval_minutes=5, jitter=30, is_leader_only=True)

    async def run(self):
        query = "MATCH (u:User) WHERE u.notifications_enabled = true RETURN u.id as id"
        try:
            results = await neo4j_manager.query_graph(query)
            active_uids = [res["id"] for res in results]

            if not active_uids:
                return

            logger.info(f"DueScannerBatchJob: Processing {len(active_uids)} users.")

            sem = asyncio.Semaphore(10)

            async def safe_process(uid):
                async with sem:
                    try:
                        await scan_due_tasks(uid)
                    except Exception as e:
                        logger.error(f"DueScannerBatchJob error for user {uid}: {e}")

            await asyncio.gather(*(safe_process(uid) for uid in active_uids))

        except Exception as e:
            logger.error(f"DueScannerBatchJob failed: {e}")
