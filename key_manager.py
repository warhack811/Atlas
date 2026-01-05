"""
ATLAS Yönlendirici - Profesyonel API Anahtarı Yöneticisi (Key Manager)
---------------------------------------------------------------------
Bu bileşen, birden fazla sağlayıcıdan (Groq, Gemini vb.) gelen API anahtarlarının
yönetiminden, rotasyonundan ve sağlık durumunun takibinden sorumludur.

Temel Sorumluluklar:
1. Anahtar Rotasyonu: İstekleri anahtarlar arasında dengeli (least-loaded) dağıtma.
2. Hız Sınırı Koruması (429): Rate-limit aşımında anahtarı geçici soğumaya (cooldown) alma.
3. Sağlık Takibi: Başarı/Hata oranlarına göre en güvenilir anahtarı seçme.
4. Kota Yönetimi: Günlük veya model bazlı kota dolduğunda anahtarı otomatik devre dışı bırakma.
5. Çoklu Sağlayıcı Desteği: Google Gemini ve Groq için ayrı anahtar havuzları yönetme.
"""

import time
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class KeyStatus(Enum):
    """API anahtarının güncel durumunu belirten sınıflar."""
    HEALTHY = "healthy"      # Sağlıklı, kullanıma uygun
    COOLDOWN = "cooldown"    # Geçici sınırlama (429) nedeniyle beklemede
    EXHAUSTED = "exhausted"  # Günlük veya model kotası tamamen dolmuş
    DISABLED = "disabled"    # Manuel olarak devre dışı bırakılmış


@dataclass
class KeyStats:
    """Bir API anahtarına ait performans ve kullanım istatistikleri."""
    key_id: str
    key_masked: str  # Güvenlik için sadece son 4 karakteri saklanır
    status: KeyStatus = KeyStatus.HEALTHY
    
    # Kullanım Sayaçları
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rate_limit_hits: int = 0
    
    # Model Bazlı Kullanım Takibi
    model_usage: dict = field(default_factory=dict)  # {model_id: count}
    
    # Zamanlama ve Cooldown Bilgileri
    last_used: Optional[datetime] = None
    cooldown_until: Optional[datetime] = None
    last_error: Optional[str] = None
    
    # Model exhaustion (Quota errors)
    # {model_id: reset_time}
    model_exhausted: dict = field(default_factory=dict)
    
    # Günlük Sayaçlar (Gece yarısı sıfırlanır)
    daily_requests: int = 0
    daily_reset_date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    
    @property
    def success_rate(self) -> float:
        """Başarı oranı hesapla."""
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests
    
    def is_available(self, model_id: Optional[str] = None) -> bool:
        """Anahtarın o an ve o model için kullanılabilir olup olmadığını denetler."""
        if self.status == KeyStatus.DISABLED:
            return False
            
        # Check model-specific exhaustion
        if model_id and model_id in self.model_exhausted:
            reset_time = self.model_exhausted[model_id]
            if datetime.now() < reset_time:
                return False
            else:
                # Local reset time passed
                del self.model_exhausted[model_id]

        if self.status == KeyStatus.COOLDOWN:
            if self.cooldown_until and datetime.now() < self.cooldown_until:
                return False
            # Cooldown bitti, healthy'ye dön
            self.status = KeyStatus.HEALTHY
        return True
    
    def to_dict(self) -> dict:
        """Debug için dict dönüşümü."""
        return {
            "key_id": self.key_id,
            "key_masked": self.key_masked,
            "status": self.status.value,
            "success_rate": round(self.success_rate, 2),
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "daily_requests": self.daily_requests,
            "rate_limit_hits": self.rate_limit_hits,
            "is_available": self.is_available,
            "model_usage": self.model_usage,
            "last_used": self.last_used.isoformat() if self.last_used else None
        }


class KeyManager:
    """
    Kurumsal API Anahtarı Yöneticisi - Çoklu sağlayıcı rotasyonu.
    """
    
    _pools: dict[str, dict[str, KeyStats]] = {"groq": {}, "gemini": {}}
    _cooldown_seconds: int = 60
    _initialized: bool = False
    
    @classmethod
    def initialize(cls, groq_keys: list[str] = None, gemini_keys: list[str] = None) -> None:
        """Key'leri havuzlara yükle."""
        if groq_keys:
            cls._pools["groq"] = {}
            for i, key in enumerate(groq_keys):
                if not key: continue
                key_id = f"groq_{i+1}"
                stats = KeyStats(key_id=key_id, key_masked=f"...{key[-4:]}" if len(key) > 4 else "****")
                stats._actual_key = key
                cls._pools["groq"][key_id] = stats
        
        if gemini_keys:
            cls._pools["gemini"] = {}
            for i, key in enumerate(gemini_keys):
                if not key: continue
                key_id = f"gemini_{i+1}"
                stats = KeyStats(key_id=key_id, key_masked=f"...{key[-4:]}" if len(key) > 4 else "****")
                stats._actual_key = key
                cls._pools["gemini"][key_id] = stats
        
        cls._initialized = True
    
    @classmethod
    def get_best_key(cls, model_id: Optional[str] = None) -> Optional[str]:
        """Model ID'ye ve performans verilerine göre en uygun anahtarı seçer."""
        if not cls._initialized:
            cls._auto_initialize()
        
        provider = cls._detect_provider(model_id)
        if provider not in cls._pools:
            return None
            
        cls._check_daily_reset()
        
        available_keys = [
            stats for stats in cls._pools[provider].values()
            if stats.is_available(model_id)
        ]
        
        if not available_keys:
            return None
        
        # Seçim kriteri: En az günlük istek ve en yüksek başarı oranı
        best = sorted(
            available_keys,
            key=lambda k: (k.daily_requests, -k.success_rate)
        )[0]
        
        return best._actual_key
    
    @classmethod
    def report_success(cls, api_key: str, model_id: str = None) -> None:
        """Başarılı çağrı bildir."""
        stats = cls._find_by_key(api_key)
        if stats:
            stats.total_requests += 1
            stats.successful_requests += 1
            stats.daily_requests += 1
            stats.last_used = datetime.now()
            if model_id:
                stats.model_usage[model_id] = stats.model_usage.get(model_id, 0) + 1
    
    @classmethod
    def report_error(cls, api_key: str, status_code: int = 0, error_msg: str = "", model_id: str = None) -> None:
        """Hatayı kaydeder ve hata tipine göre anahtarı cooldown veya kota aşımına alır."""
        stats = cls._find_by_key(api_key)
        if not stats: return
        
        stats.total_requests += 1
        stats.failed_requests += 1
        stats.daily_requests += 1
        stats.last_used = datetime.now()
        stats.last_error = error_msg or f"HTTP {status_code}"
        
        error_lower = error_msg.lower()
        # 1. Kota Aşımı (Model bazlı kalıcı engel)
        is_quota = any(x in error_lower for x in ["quota", "exhausted", "limit exceeded"])
        if is_quota and model_id:
            from datetime import timedelta
            now = datetime.now()
            reset_time = datetime(now.year, now.month, now.day) + timedelta(days=1)
            stats.model_exhausted[model_id] = reset_time
            return

        # 2. Kapasite Sorunu (503) -> DagExecutor bunu bir sonraki modelle telafi eder
        if status_code == 503 or "over capacity" in error_lower:
            return

        # 3. Standart Hız Sınırı (429) -> Geçici soğuma süresi başlat
        if status_code == 429:
            stats.rate_limit_hits += 1
            stats.status = KeyStatus.COOLDOWN
            from datetime import timedelta
            stats.cooldown_until = datetime.now() + timedelta(seconds=cls._cooldown_seconds)
    
    @classmethod
    def get_stats(cls) -> list[dict]:
        """Tüm key istatistiklerini getir."""
        if not cls._initialized: cls._auto_initialize()
        res = []
        for pool in cls._pools.values():
            res.extend([stats.to_dict() for stats in pool.values()])
        return res
    
    @classmethod
    def get_total_key_count(cls, model_id: str = None) -> int:
        """Sağlayıcıdaki toplam key sayısı."""
        if not cls._initialized: cls._auto_initialize()
        provider = cls._detect_provider(model_id)
        return len(cls._pools.get(provider, {}))
    
    @classmethod
    def get_available_count(cls, model_id: str = None) -> int:
        """Kullanılabilir key sayısı."""
        if not cls._initialized: cls._auto_initialize()
        provider = cls._detect_provider(model_id)
        pool = cls._pools.get(provider, {})
        return sum(1 for stats in pool.values() if stats.is_available(model_id))

    @classmethod
    def _detect_provider(cls, model_id: str) -> str:
        """Model adına göre sağlayıcıyı belirle."""
        if not model_id: return "groq"
        mid = model_id.lower()
        if any(x in mid for x in ["gemini", "google"]):
            return "gemini"
        return "groq"
    
    @classmethod
    def _find_by_key(cls, api_key: str) -> Optional[KeyStats]:
        """Key'e göre hangi havuzda olursa olsun stats bul."""
        for pool in cls._pools.values():
            for stats in pool.values():
                if hasattr(stats, '_actual_key') and stats._actual_key == api_key:
                    return stats
        return None
    
    @classmethod
    def _check_daily_reset(cls) -> None:
        """Günlük sayaçları sıfırla."""
        today = datetime.now().strftime("%Y-%m-%d")
        for pool in cls._pools.values():
            for stats in pool.values():
                if stats.daily_reset_date != today:
                    stats.daily_requests = 0
                    stats.daily_reset_date = today
                    stats.model_exhausted = {} # Ayrıca kotaları da sıfırla
    
    @classmethod
    def _auto_initialize(cls) -> None:
        """Otomatik initialize (config'den key'leri al)."""
        from .config import get_groq_api_keys, get_gemini_api_keys
        cls.initialize(groq_keys=get_groq_api_keys(), gemini_keys=get_gemini_api_keys())
