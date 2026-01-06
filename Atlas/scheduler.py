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

logger = logging.getLogger(__name__)

# Merkezi Zamanlayıcı Nesnesi (Singleton)
scheduler = AsyncIOScheduler()

def start_scheduler():
    """Arka plan zamanlayıcısını ve tanımlı tüm görevleri başlatır.
    FAZ0.1-5: test_user sabiti kaldırıldı. Observer job'ları Faz 7'de user listesinden eklenecek.
    """
    if not scheduler.running:
        # TODO: Faz 7'de user listesi DB/config'den alınıp her kullanıcı için observer job eklenecek
        # Şimdilik scheduler boş başlatılıyor
        
        scheduler.start()
        logger.info("Scheduler başarıyla başlatıldı (Observer job'ları manuel olarak eklenecek).")

def stop_scheduler():
    """Zamanlayıcıyı ve çalışan görevleri güvenli bir şekilde kapatır."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler durduruldu.")
