from atlas.tasks import BaseJob, JobConfig, register_job
from atlas.memory.neo4j_manager import neo4j_manager
from atlas.services.generator import generate_response
from atlas.config import CONSOLIDATION_SETTINGS, MODEL_GOVERNANCE
import logging

logger = logging.getLogger(__name__)

EPISODE_WORKER_PROMPT = """
Aşağıdaki konuşma dökümünü kullanarak kısa ve öz bir oturum özeti (episodic memory) oluştur.
Sadece verilen metni kullan, uydurma bilgi ekleme.
Dil: Türkçe
"""

@register_job
class EpisodeWorkerJob(BaseJob):
    """PENDING episodeları tarayan ve özetleyen worker job."""
    name = "episode_worker"
    config = JobConfig(interval_minutes=2, jitter=15, is_leader_only=True)

    async def run(self):
        episode = await neo4j_manager.claim_pending_episode()
        if not episode: return

        ep_id = episode["id"]
        user_id = episode["user_id"]
        session_id = episode["session_id"]
        
        try:
            logger.info(f"Episode Worker: İşleniyor -> {ep_id}")
            turns = await neo4j_manager.get_recent_turns(user_id, session_id, limit=40)
            relevant_turns = [t for t in turns if episode["start_turn"] <= t["turn_index"] <= episode["end_turn"]]
            
            if not relevant_turns:
                await neo4j_manager.mark_episode_failed(ep_id, "No turns found")
                return

            transcript = "\n".join([f"{t['role']}: {t['content']}" for t in relevant_turns])
            model_id = MODEL_GOVERNANCE.get("episodic_summary", ["gemini-2.0-flash"])[0]
            
            result = await generate_response(f"{EPISODE_WORKER_PROMPT}\nDÖKÜM:\n{transcript}", model_id, "analysis")
            
            if result.ok:
                from atlas.memory.episode_pipeline import finalize_episode_with_vectors
                await finalize_episode_with_vectors(ep_id, user_id, session_id, result.text, result.model)
                logger.info(f"Episode Worker: Tamamlandı -> {ep_id}")
            else:
                await neo4j_manager.mark_episode_failed(ep_id, result.text)
        except Exception as e:
            logger.exception(f"Episode Worker Hata: {ep_id}")
            await neo4j_manager.mark_episode_failed(ep_id, str(e))

@register_job
class ConsolidationJob(BaseJob):
    """Eski episodları konsolide eden job."""
    name = "consolidate"
    config = JobConfig(interval_minutes=60, jitter=60, is_leader_only=True)

    async def run(self):
        if not CONSOLIDATION_SETTINGS.get("ENABLE_CONSOLIDATION", True): return

        # Bekleyen işleri tetikle/bul
        query = "MATCH (s:Session) RETURN s.id as id"
        sessions = await neo4j_manager.query_graph(query)
        for s in sessions:
            await neo4j_manager.create_consolidation_pending(s['id'], 
                CONSOLIDATION_SETTINGS["CONSOLIDATION_EPISODE_WINDOW"], 
                CONSOLIDATION_SETTINGS["CONSOLIDATION_MIN_AGE_DAYS"])

        cons = await neo4j_manager.claim_pending_consolidation()
        if not cons: return

        cons_id = cons["id"]
        try:
            episodes = await neo4j_manager.get_episodes_by_ids(cons["source_ids"])
            if not episodes: return
            
            combined = "\n---\n".join([e['summary'] for e in episodes])
            model_id = MODEL_GOVERNANCE.get("episodic_summary", ["gemini-2.0-flash"])[0]
            
            result = await generate_response(f"Konsolide et:\n{combined}", model_id, "analysis")
            if result.ok:
                from atlas.memory.episode_pipeline import finalize_episode_with_vectors
                await finalize_episode_with_vectors(cons_id, cons.get("user_id"), cons.get("session_id"), result.text, result.model)
                logger.info(f"Consolidation: Tamamlandı -> {cons_id}")
        except Exception as e:
            logger.exception(f"Consolidation Hata: {cons_id}")
            await neo4j_manager.mark_episode_failed(cons_id, str(e))
