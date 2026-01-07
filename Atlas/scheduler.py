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

# Merkezi Zamanlayıcı Nesnesi (Singleton)
scheduler = AsyncIOScheduler()

async def start_scheduler():
    """Arka plan zamanlayıcısını ve tanımlı tüm görevleri başlatır.
    FAZ 7: Veritabanındaki aktif kullanıcılar için job'ları kaydeder.
    """
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler başlatıldı. Aktif kullanıcılar taranıyor...")
        
        # 1. Aktif kullanıcıları bul (Opt-in olanlar)
        query = "MATCH (u:User) WHERE u.notifications_enabled = true RETURN u.id as id"
        try:
            users = await neo4j_manager.query_graph(query)
            
            for user in users:
                user_id = user["id"]
                
                # a) Observer Job (15 dk)
                obs_job_id = f"obs:{user_id}"
                if not scheduler.get_job(obs_job_id):
                    scheduler.add_job(
                        observer.check_triggers,
                        trigger=IntervalTrigger(minutes=15),
                        args=[user_id],
                        id=obs_job_id,
                        replace_existing=True
                    )
                    logger.info(f"Dinamik Job eklendi: {obs_job_id}")

                # b) Due Task Scanner Job (5 dk)
                due_job_id = f"due:{user_id}"
                if not scheduler.get_job(due_job_id):
                    scheduler.add_job(
                        scan_due_tasks,
                        trigger=IntervalTrigger(minutes=5),
                        args=[user_id],
                        id=due_job_id,
                        replace_existing=True
                    )
                    logger.info(f"Dinamik Job eklendi: {due_job_id}")

            logger.info(f"Scheduler: {len(users)} kullanıcı için job'lar hazır.")
        except Exception as e:
            logger.error(f"Scheduler başlatma hatası (DB erişimi): {e}")

async def refresh_scheduler_jobs():
    """Zamanlayıcıdaki job'ları günceller (Yeni kullanıcılar veya ayar değişiklikleri için)."""
    if scheduler.running:
        await start_scheduler()

def stop_scheduler():
    """Zamanlayıcıyı ve çalışan görevleri güvenli bir şekilde kapatır."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler durduruldu.")
