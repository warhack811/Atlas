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
from .observer import observer

logger = logging.getLogger(__name__)

# Merkezi Zamanlayıcı Nesnesi (Singleton)
scheduler = AsyncIOScheduler()

def start_scheduler():
    """Arka plan zamanlayıcısını ve tanımlı tüm görevleri başlatır."""
    if not scheduler.running:
        # Örnek: 'test_user' için her 15 dakikada bir kontrol et
        # Test amaçlı süreyi düşürebiliriz ama talep 15 dk.
        scheduler.add_job(
            observer.check_triggers,
            trigger=IntervalTrigger(minutes=15),
            args=["test_user"], # Şimdilik sabit bir test kullanıcısı
            id="observer_job_test_user",
            replace_existing=True
        )
        
        scheduler.start()
        logger.info("Scheduler, Gözlemci görevi ile birlikte başarıyla başlatıldı.")

def stop_scheduler():
    """Zamanlayıcıyı ve çalışan görevleri güvenli bir şekilde kapatır."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler durduruldu.")
