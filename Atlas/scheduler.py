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

logger = logging.getLogger(__name__)

import uuid
import socket

# Her instance için benzersiz bir ID (Leader seçimi için)
INSTANCE_ID = f"{socket.gethostname()}:{uuid.uuid4().hex[:6]}"

# Merkezi Zamanlayıcı Nesnesi (Singleton)
scheduler = AsyncIOScheduler()

# Global Liderlik Durumu
_IS_LEADER = False

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

async def _demote_to_follower():
    """Instance'ı FOLLOWER moduna düşürür ve lider görevlerini temizler."""
    global _IS_LEADER
    _IS_LEADER = False
    logger.warning(f"Scheduler: {INSTANCE_ID} Liderliği KAYBETTİ veya devretti. Lider görevleri temizleniyor.")
    
    # Lider görevlerini kaldır
    leader_job_ids = ["leader_heartbeat"]
    # obs:* ve due:* işlerini de kaldır (Sadece liderde çalışmalı)
    for job in scheduler.get_jobs():
        if job.id.startswith(("obs:", "due:", "leader_heartbeat")):
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
