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

async def start_scheduler():
    """Arka plan zamanlayıcısını ve tanımlı tüm görevleri başlatır.
    FAZ 7-R: Leader Lock kontrolü ve dinamik job kaydı.
    """
    if scheduler.running:
        await refresh_scheduler_jobs()
        return

    # 1. LEADER LOCK KONTROLÜ (Dinamik dağıtık kilit)
    # TTL: 90 saniye (kalp atışı her 60 saniyede bir tazelenmeli)
    is_leader = await neo4j_manager.try_acquire_lock("global_scheduler", INSTANCE_ID, 90)
    
    if not is_leader:
        logger.info(f"Scheduler: {INSTANCE_ID} lider kilidini alamadı. Yedek modda bekleniyor.")
        return

    scheduler.start()
    logger.info(f"Scheduler: {INSTANCE_ID} LİDER olarak başlatıldı.")
    
    # 2. Kalp atışı (Lock Refresh) görevi ekle
    scheduler.add_job(
        _refresh_leader_lock,
        trigger=IntervalTrigger(seconds=60),
        id="leader_heartbeat",
        replace_existing=True
    )
    
    await refresh_scheduler_jobs()

async def _refresh_leader_lock():
    """Liderlik kilidini periyodik olarak tazeler."""
    success = await neo4j_manager.try_acquire_lock("global_scheduler", INSTANCE_ID, 90)
    if not success:
        logger.warning("Scheduler: Liderlik kilidi tazelenemedi! Durduruluyor...")
        stop_scheduler()

async def sync_scheduler_jobs():
    """
    Kullanıcı bazlı job'ları (observer, due_scanner) veritabanı ile senkronize eder (RC-1 Hardening).
    Aktif olanları ekler, devre dışı kalanları (opt-out) temizler.
    """
    if not scheduler.running:
        logger.warning("Sync çağrıldı ama scheduler çalışmıyor.")
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
