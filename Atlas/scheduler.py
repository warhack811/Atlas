"""
ATLAS Yönlendirici - Görev Zamanlayıcı (Scheduler)
-------------------------------------------------
Bu bileşen, arka planda belirli aralıklarla çalışması gereken görevleri 
(örn: proaktif gözlemci kontrolleri) yönetir.

Temel Sorumluluklar:
1. Görev Zamanlama: Belirli periyotlarda (15 dakikada bir vb.) işleri tetikleme.
2. Yaşam Döngüsü Yönetimi: Uygulama başladığında/kapandığında scheduler'ı yönetme.
3. Gözlemci Entegrasyonu: Observer sınıfı aracılığıyla kullanıcı verilerini tarama.
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from Atlas.observer import observer
from Atlas.memory.neo4j_manager import neo4j_manager
from Atlas.memory.due_scanner import scan_due_tasks
from Atlas.generator import generate_response
from Atlas.config import RETENTION_SETTINGS, CONSOLIDATION_SETTINGS

logger = logging.getLogger(__name__)

import uuid
import socket

# Her instance için benzersiz bir ID (Leader seçimi için)
INSTANCE_ID = f"{socket.gethostname()}:{uuid.uuid4().hex[:6]}"

# Merkezi Zamanlayıcı Nesnesi (Singleton)
scheduler = AsyncIOScheduler()

# Global Liderlik Durumu
_IS_LEADER = False

EPISODE_WORKER_PROMPT = """
Aşağıdaki konuşma dökümünü kullanarak kısa ve öz bir oturum özeti (episodic memory) oluştur.
Sadece verilen metni kullan, uydurma bilgi ekleme.

Çıktı formatı:
### Oturum Özeti
- [Madde 1]
- ...
- [Madde 6-10]

### Açık Sorular / Kararlar
- [Madde 1-3]

Dil: Türkçe
"""

CONSOLIDATION_WORKER_PROMPT = """
Aşağıdaki episod özetlerini (episodic memories) kullanarak daha üst seviye bir konsolide dönem özeti oluştur.
Sadece verilen özetlerdeki bilgileri kullan, uydurma yapma.

Çıktı formatı:
### Dönem Özeti
- [Madde 1]
- ...
- [Madde 6-10]

### Açık Konular / Bekleyen İşler
- [Madde 1-3]

Dil: Türkçe
"""

async def start_scheduler():
    """Arka plan zamanlayıcısını başlatır. (RC-2 Hardening)
    Tüm instance'larda her zaman çalışır ve periyodik olarak liderlik için yarışır.
    """
    if scheduler.running:
        return

    scheduler.start()
    logger.info(f"Scheduler: {INSTANCE_ID} başlatıldı (Follower modunda).")

    # Leader Election job'u her zaman çalışır (30 saniyede bir)
    scheduler.add_job(
        check_leader_election,
        trigger=IntervalTrigger(seconds=30),
        id="leader_election",
        replace_existing=True
    )
    
    # İlk kontrolü hemen yap
    await check_leader_election()

async def check_leader_election():
    """Liderlik durumunu kontrol eder ve gerekirse promote/demote işlemlerini yapar."""
    global _IS_LEADER
    
    # Liderlik kilidini almaya çalış (TTL: 90sn)
    is_leader_now = await neo4j_manager.try_acquire_lock("global_scheduler", INSTANCE_ID, 90)
    
    if is_leader_now:
        if not _IS_LEADER:
            await _promote_to_leader()
    else:
        if _IS_LEADER:
            await _demote_to_follower()

async def _promote_to_leader():
    """Instance'ı LİDER moduna yükseltir ve lider görevlerini başlatır."""
    global _IS_LEADER
    _IS_LEADER = True
    logger.info(f"Scheduler: {INSTANCE_ID} LİDER olarak atandı! Görevler başlatılıyor.")
    
    # 1. Kalp atışı (Lock Refresh) görevi ekle (Lider'de 60 saniyede bir)
    scheduler.add_job(
        _refresh_leader_lock,
        trigger=IntervalTrigger(seconds=60),
        id="leader_heartbeat",
        replace_existing=True
    )
    
    # 2. İşleri senkronize et (Observer/Due Scanner)
    await refresh_scheduler_jobs()

    # 3. Episode Worker job'u ekle (2 dakikada bir)
    scheduler.add_job(
        run_episode_worker,
        trigger=IntervalTrigger(minutes=2),
        id="episode_worker",
        replace_existing=True
    )

    # 4. Maintenance Job (Her gün 03:30'da çalışacak şekilde interval simülasyonu veya daily trigger)
    scheduler.add_job(
        run_maintenance_worker,
        trigger=IntervalTrigger(hours=24),
        id="maintenance",
        replace_existing=True
    )

    # 5. Consolidation Job (Her 60 dakikada bir)
    if CONSOLIDATION_SETTINGS.get("ENABLE_CONSOLIDATION", True):
        scheduler.add_job(
            run_consolidation_worker,
            trigger=IntervalTrigger(minutes=60),
            id="consolidate",
            replace_existing=True
        )

async def _demote_to_follower():
    """Instance'ı FOLLOWER moduna düşürür ve lider görevlerini temizler."""
    global _IS_LEADER
    _IS_LEADER = False
    logger.warning(f"Scheduler: {INSTANCE_ID} Liderliği KAYBETTİ veya devretti. Lider görevleri temizleniyor.")
    
    # Lider görevlerini kaldır
    leader_job_ids = ["leader_heartbeat"]
    # obs:* ve due:* işlerini de kaldır (Sadece liderde çalışmalı)
    for job in scheduler.get_jobs():
        if job.id.startswith(("obs:", "due:", "leader_heartbeat", "episode_worker", "maintenance", "consolidate")):
            scheduler.remove_job(job.id)
            logger.debug(f"Job kaldırıldı (Demote): {job.id}")

async def _refresh_leader_lock():
    """Liderlik kilidini periyodik olarak tazeler."""
    success = await neo4j_manager.try_acquire_lock("global_scheduler", INSTANCE_ID, 90)
    if not success:
        logger.warning("Scheduler: Liderlik kilidi tazelenemedi!")
        await _demote_to_follower()

async def sync_scheduler_jobs():
    """
    Kullanıcı bazlı job'ları (observer, due_scanner) veritabanı ile senkronize eder (RC-1 Hardening).
    Aktif olanları ekler, devre dışı kalanları (opt-out) temizler.
    """
    if not scheduler.running or not _IS_LEADER:
        logger.debug("Sync atlanıyor: Scheduler çalışmıyor veya instance lider değil.")
        return
        
    logger.info("Scheduler: Kullanıcı job'ları senkronize ediliyor...")
    
    # 1. Aktif (opt-in) kullanıcıları bul
    query = "MATCH (u:User) WHERE u.notifications_enabled = true RETURN u.id as id"
    try:
        results = await neo4j_manager.query_graph(query)
        active_uids = {res["id"] for res in results}
        
        # 2. Mevcut job'ları tara
        current_jobs = scheduler.get_jobs()
        existing_job_ids = {job.id for job in current_jobs}
        
        # 3. Yeni/Eski job senkronizasyonu
        for uid in active_uids:
            # Observer Job (15 dk)
            obs_id = f"obs:{uid}"
            if obs_id not in existing_job_ids:
                scheduler.add_job(
                    observer.check_triggers,
                    trigger=IntervalTrigger(minutes=15),
                    args=[uid],
                    id=obs_id,
                    replace_existing=True
                )
                logger.debug(f"Job eklendi: {obs_id}")
            
            # Due Task Scanner Job (5 dk)
            due_id = f"due:{uid}"
            if due_id not in existing_job_ids:
                scheduler.add_job(
                    scan_due_tasks,
                    trigger=IntervalTrigger(minutes=5),
                    args=[uid],
                    id=due_id,
                    replace_existing=True
                )
                logger.debug(f"Job eklendi: {due_id}")

        # 4. Devre dışı kalan kullanıcıları temizle (Dynamic Cleanup)
        for jid in list(existing_job_ids):
            if jid.startswith(("obs:", "due:")):
                parts = jid.split(":")
                uid_in_job = parts[1] if len(parts) > 1 else ""
                if uid_in_job not in active_uids:
                    scheduler.remove_job(jid)
                    logger.info(f"Job kaldırıldı (Kullanıcı opt-out veya pasif): {jid}")

        logger.info(f"Scheduler: Senkronizasyon tamamlandı ({len(active_uids)} aktif kullanıcı)")
    except Exception as e:
        logger.error(f"Job senkronizasyon hatası: {e}")

async def run_episode_worker():
    """PENDING episodeları tarayan ve özetleyen worker job. (RC-4)"""
    if not _IS_LEADER: return

    logger.debug("Episode Worker: Bekleyen işler kontrol ediliyor...")
    
    # 1. Bekleyen bir iş al (claim)
    episode = await neo4j_manager.claim_pending_episode()
    if not episode:
        return

    ep_id = episode["id"]
    user_id = episode["user_id"]
    session_id = episode["session_id"]
    start = episode["start_turn"]
    end = episode["end_turn"]

    try:
        logger.info(f"Episode Worker: İşleniyor -> {ep_id}")
        
        # 2. Turn metinlerini getir
        turns = await neo4j_manager.get_recent_turns(user_id, session_id, limit=40) # Geniş limit
        # Sadece ilgili aralıktaki turnleri filtrele
        relevant_turns = [t for t in turns if start <= t["turn_index"] <= end]
        
        if not relevant_turns:
            await neo4j_manager.mark_episode_failed(ep_id, "No turns found in range")
            return

        # 3. Metni birleştir
        transcript = "\n".join([f"{'Kullanıcı' if t['role']=='user' else 'Atlas'}: {t['content']}" for t in relevant_turns])
        
        # 4. LLM ile özetle
        from Atlas.config import MODEL_GOVERNANCE
        model_id = MODEL_GOVERNANCE.get("episodic_summary", ["gemini-2.0-flash"])[0]
        
        message = f"DÖKÜM:\n{transcript}\n\nÖzetle."
        # Not: generate_response model_id ve intent=analysis (structured output formatı için uygun)
        result = await generate_response(message, model_id, "analysis", style_profile={"persona": "standard"})
        
        if result.ok:
            await neo4j_manager.mark_episode_ready(ep_id, result.text, result.model)
            logger.info(f"Episode Worker: Tamamlandı -> {ep_id}")
        else:
            await neo4j_manager.mark_episode_failed(ep_id, result.text)
            logger.error(f"Episode Worker: LLM hatası -> {ep_id}: {result.text}")

    except Exception as e:
        logger.exception(f"Episode Worker: Kritik hata -> {ep_id}")
        await neo4j_manager.mark_episode_failed(ep_id, str(e))

async def run_maintenance_worker():
    """Arka planda veri temizliği yapan job (RC-6)."""
    if not _IS_LEADER: return
    
    logger.info("Maintenance Worker: Temizlik başlatıldı...")
    try:
        r = RETENTION_SETTINGS
        await neo4j_manager.prune_turns(r["TURN_RETENTION_DAYS"], r["MAX_TURNS_PER_SESSION"])
        await neo4j_manager.prune_episodes(r["EPISODE_RETENTION_DAYS"])
        await neo4j_manager.prune_notifications(r["NOTIFICATION_RETENTION_DAYS"])
        await neo4j_manager.prune_tasks(r["DONE_TASK_RETENTION_DAYS"])
        logger.info("Maintenance Worker: Temizlik tamamlandı.")
    except Exception as e:
        logger.error(f"Maintenance Worker: Hata -> {e}")

async def run_consolidation_worker():
    """Eski episodları konsolide eden job (RC-6)."""
    if not _IS_LEADER: return
    
    logger.debug("Consolidation Worker: Kontrol ediliyor...")
    
    # 1. Önce pending konsolidasyonları kontrol et ve oluştur (İstisna: çok fazla session varsa batchlemek gerekebilir)
    # Şimdilik READY REGULAR episodi window'dan fazla olan tüm sessionlar için pending oluşturmayı tetikle
    query = "MATCH (s:Session) RETURN s.id as id"
    sessions = await neo4j_manager.query_graph(query)
    c = CONSOLIDATION_SETTINGS
    for s in sessions:
        await neo4j_manager.create_consolidation_pending(s['id'], c["CONSOLIDATION_EPISODE_WINDOW"], c["CONSOLIDATION_MIN_AGE_DAYS"])

    # 2. Bekleyen bir consolidation işi al
    cons = await neo4j_manager.claim_pending_consolidation()
    if not cons:
        return

    cons_id = cons["id"]
    source_ids = cons["source_ids"]
    
    try:
        logger.info(f"Consolidation Worker: İşleniyor -> {cons_id}")
        
        # 3. Kaynak episodların özetlerini çek
        episodes = await neo4j_manager.get_episodes_by_ids(source_ids)
        if not episodes:
             await neo4j_manager.mark_episode_failed(cons_id, "Source episodes not found")
             return
             
        # Kronolojik sıra (id içinde turn index varsa ona göre sort etsek iyi olur ama şimdilik liste sırası)
        combined_summaries = "\n---\n".join([e['summary'] for e in episodes])
        
        # 4. LLM ile Konsolidasyon
        from Atlas.config import MODEL_GOVERNANCE
        model_id = MODEL_GOVERNANCE.get("episodic_summary", ["gemini-2.0-flash"])[0]
        
        prompt = f"{CONSOLIDATION_WORKER_PROMPT}\n\nKAYNAK ÖZETLER:\n{combined_summaries}"
        result = await generate_response(prompt, model_id, "analysis", style_profile={"persona": "standard"})
        
        if result.ok:
            await neo4j_manager.mark_episode_ready(cons_id, result.text, result.model)
            logger.info(f"Consolidation Worker: Tamamlandı -> {cons_id}")
        else:
            await neo4j_manager.mark_episode_failed(cons_id, result.text)
            logger.error(f"Consolidation Worker: LLM hatası -> {cons_id}: {result.text}")

    except Exception as e:
        logger.exception(f"Consolidation Worker: Kritik hata -> {cons_id}")
        await neo4j_manager.mark_episode_failed(cons_id, str(e))

async def refresh_scheduler_jobs():
    """Zamanlayıcıdaki job'ları günceller (sync_scheduler_jobs alias)."""
    await sync_scheduler_jobs()

def stop_scheduler():
    """Zamanlayıcıyı ve çalışan görevleri güvenli bir şekilde kapatır."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler durduruldu.")
        # Kilidi serbest bırakmayı deneyelim (Optional)
        asyncio.create_task(neo4j_manager.release_lock("global_scheduler", INSTANCE_ID))
