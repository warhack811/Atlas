"""
ATLAS Yönlendirici - Bütçe ve Kullanım Takibi (Budget Tracker)
-------------------------------------------------------------
Bu bileşen, modellerin ve API anahtarlarının günlük kullanım miktarlarını
takip eder, bütçe sınırlarını denetler ve belirlenen eşik değerleri 
aşıldığında uyarılar üretir.

Temel Sorumluluklar:
1. Limit Yönetimi: Model bazlı günlük istek (RPD) ve token (TPD) sınırlarını tanımlama.
2. Kullanım Kaydı: Her asenkron çağrı sonrası harcanan kaynakları hafızada saklama.
3. Otomatik Sıfırlama: Her gece yarısı (00:00) kullanım sayaçlarını sıfırlama.
4. Eşik Uyarıları: Kota doluluk oranına göre (%80, %90, %100) farklı seviyelerde uyarı verme.
5. İstatistik Raporlama: Sistem genelinde hangi modelin ne kadar kaynak tükettiğini analiz etme.
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Dict, Optional, List, Tuple
from enum import Enum
import threading


class AlertLevel(Enum):
    """Uyarı seviyeleri."""
    NORMAL = "normal"      # < %80
    WARNING = "warning"    # >= %80
    CRITICAL = "critical"  # >= %90
    EXCEEDED = "exceeded"  # >= %100


@dataclass
class ModelLimits:
    """Bir model için tanımlanan günlük fiziksel veya finansal limitler."""
    rpd: int  # Günlük İstek Sayısı (Request Per Day)
    tpd: int  # Günlük Token Sayısı (Token Per Day)


@dataclass
class UsageRecord:
    """Gerçekleşen kullanım verilerini saklayan veri sınıfı."""
    requests: int = 0
    tokens: int = 0
    last_updated: datetime = field(default_factory=datetime.now)


@dataclass
class BudgetAlert:
    """Bütçe sınırlarına yaklaşıldığında veya aşıldığında oluşturulan uyarı objesi."""
    model_id: str
    metric: str  # 'requests' veya 'tokens'
    level: AlertLevel
    current: int
    limit: int
    percentage: float
    timestamp: datetime = field(default_factory=datetime.now)


class BudgetTracker:
    """
    Model ve API anahtarı bazlı bütçe ve kota takip kontrolcüsü.
    """
    
    # Varsayılan model limitleri (4 key ile)
    DEFAULT_LIMITS: Dict[str, ModelLimits] = {
        "llama-3.1-8b-instant": ModelLimits(rpd=57600, tpd=5_000_000),
        "llama-3.3-70b-versatile": ModelLimits(rpd=4000, tpd=1_000_000),
        "llama-guard-3-8b": ModelLimits(rpd=57600, tpd=5_000_000),
        "llama-4-scout-17b-16e-instruct": ModelLimits(rpd=4000, tpd=1_000_000),
        "qwen-qwq-32b": ModelLimits(rpd=4000, tpd=1_000_000),
        "moonshotai/kimi-k2-instruct": ModelLimits(rpd=4000, tpd=1_000_000),
        "meta-llama/llama-4-maverick-17b-128e-instruct": ModelLimits(rpd=4000, tpd=1_000_000),
    }
    
    # Varsayılan limit (bilinmeyen modeller için)
    FALLBACK_LIMITS = ModelLimits(rpd=1000, tpd=500_000)
    
    # Eşik değerleri
    THRESHOLD_WARNING = 0.80   # %80
    THRESHOLD_CRITICAL = 0.90  # %90
    THRESHOLD_EXCEEDED = 1.00  # %100
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._usage: Dict[str, UsageRecord] = {}  # model_id -> UsageRecord
        self._key_usage: Dict[str, UsageRecord] = {}  # key_prefix -> UsageRecord
        self._alerts: List[BudgetAlert] = []
        self._last_reset_date: date = date.today()
        self._custom_limits: Dict[str, ModelLimits] = {}
        self._initialized = True
    
    def _check_and_reset(self) -> None:
        """Gün değişikliğini kontrol et ve gerekirse sıfırla."""
        today = date.today()
        if today > self._last_reset_date:
            self._usage.clear()
            self._key_usage.clear()
            self._alerts.clear()
            self._last_reset_date = today
    
    def get_limits(self, model_id: str) -> ModelLimits:
        """Model için limitleri al."""
        if model_id in self._custom_limits:
            return self._custom_limits[model_id]
        return self.DEFAULT_LIMITS.get(model_id, self.FALLBACK_LIMITS)
    
    def set_custom_limits(self, model_id: str, rpd: int, tpd: int) -> None:
        """Özel limit tanımla."""
        self._custom_limits[model_id] = ModelLimits(rpd=rpd, tpd=tpd)
    
    def check_budget(self, model_id: str) -> Tuple[bool, Optional[str]]:
        """
        Belirli bir modelin günlük kullanım limitlerini aşıp aşmadığını denetler.
        """
        self._check_and_reset()
        
        limits = self.get_limits(model_id)
        usage = self._usage.get(model_id, UsageRecord())
        
        # RPD kontrolü
        if usage.requests >= limits.rpd:
            return False, f"Günlük istek limiti aşıldı ({usage.requests}/{limits.rpd})"
        
        # TPD kontrolü
        if usage.tokens >= limits.tpd:
            return False, f"Günlük token limiti aşıldı ({usage.tokens}/{limits.tpd})"
        
        return True, None
    
    def record_usage(
        self, 
        model_id: str, 
        tokens: int = 0,
        key_prefix: Optional[str] = None
    ) -> List[BudgetAlert]:
        """
        Gerçekleşen kullanımı kaydeder ve gerekirse uyarı tetikler.
        """
        self._check_and_reset()
        
        # Model kullanımı güncelle
        if model_id not in self._usage:
            self._usage[model_id] = UsageRecord()
        
        self._usage[model_id].requests += 1
        self._usage[model_id].tokens += tokens
        self._usage[model_id].last_updated = datetime.now()
        
        # Key kullanımı güncelle
        if key_prefix:
            if key_prefix not in self._key_usage:
                self._key_usage[key_prefix] = UsageRecord()
            self._key_usage[key_prefix].requests += 1
            self._key_usage[key_prefix].tokens += tokens
            self._key_usage[key_prefix].last_updated = datetime.now()
        
        # Uyarı kontrolü
        return self._check_thresholds(model_id)
    
    def _check_thresholds(self, model_id: str) -> List[BudgetAlert]:
        """Eşik değerlerini kontrol et ve uyarı oluştur."""
        alerts = []
        limits = self.get_limits(model_id)
        usage = self._usage.get(model_id, UsageRecord())
        
        # Request eşik kontrolü
        req_pct = usage.requests / limits.rpd if limits.rpd > 0 else 0
        req_level = self._get_alert_level(req_pct)
        
        if req_level != AlertLevel.NORMAL:
            alert = BudgetAlert(
                model_id=model_id,
                metric="requests",
                level=req_level,
                current=usage.requests,
                limit=limits.rpd,
                percentage=req_pct * 100
            )
            # Aynı seviyede tekrar uyarı verme
            if not self._alert_exists(alert):
                alerts.append(alert)
                self._alerts.append(alert)
        
        # Token eşik kontrolü
        tok_pct = usage.tokens / limits.tpd if limits.tpd > 0 else 0
        tok_level = self._get_alert_level(tok_pct)
        
        if tok_level != AlertLevel.NORMAL:
            alert = BudgetAlert(
                model_id=model_id,
                metric="tokens",
                level=tok_level,
                current=usage.tokens,
                limit=limits.tpd,
                percentage=tok_pct * 100
            )
            if not self._alert_exists(alert):
                alerts.append(alert)
                self._alerts.append(alert)
        
        return alerts
    
    def _get_alert_level(self, percentage: float) -> AlertLevel:
        """Yüzdeye göre uyarı seviyesi belirle."""
        if percentage >= self.THRESHOLD_EXCEEDED:
            return AlertLevel.EXCEEDED
        elif percentage >= self.THRESHOLD_CRITICAL:
            return AlertLevel.CRITICAL
        elif percentage >= self.THRESHOLD_WARNING:
            return AlertLevel.WARNING
        return AlertLevel.NORMAL
    
    def _alert_exists(self, new_alert: BudgetAlert) -> bool:
        """Bu uyarı zaten verildi mi kontrol et."""
        for alert in self._alerts:
            if (alert.model_id == new_alert.model_id and 
                alert.metric == new_alert.metric and 
                alert.level == new_alert.level):
                return True
        return False
    
    def get_usage_stats(self) -> Dict:
        """Tüm kullanım istatistiklerini al."""
        self._check_and_reset()
        
        stats = {
            "date": self._last_reset_date.isoformat(),
            "models": {},
            "keys": {},
            "alerts": []
        }
        
        # Model istatistikleri
        for model_id, usage in self._usage.items():
            limits = self.get_limits(model_id)
            req_pct = (usage.requests / limits.rpd * 100) if limits.rpd > 0 else 0
            tok_pct = (usage.tokens / limits.tpd * 100) if limits.tpd > 0 else 0
            
            stats["models"][model_id] = {
                "requests": {
                    "current": usage.requests,
                    "limit": limits.rpd,
                    "percentage": round(req_pct, 1),
                    "status": self._get_alert_level(req_pct / 100).value
                },
                "tokens": {
                    "current": usage.tokens,
                    "limit": limits.tpd,
                    "percentage": round(tok_pct, 1),
                    "status": self._get_alert_level(tok_pct / 100).value
                },
                "last_updated": usage.last_updated.isoformat()
            }
        
        # Key istatistikleri
        for key_prefix, usage in self._key_usage.items():
            stats["keys"][key_prefix] = {
                "requests": usage.requests,
                "tokens": usage.tokens,
                "last_updated": usage.last_updated.isoformat()
            }
        
        # Uyarılar
        for alert in self._alerts:
            stats["alerts"].append({
                "model": alert.model_id,
                "metric": alert.metric,
                "level": alert.level.value,
                "percentage": round(alert.percentage, 1),
                "timestamp": alert.timestamp.isoformat()
            })
        
        return stats
    
    def get_remaining_budget(self, model_id: str) -> Dict:
        """Model için kalan bütçeyi al."""
        self._check_and_reset()
        
        limits = self.get_limits(model_id)
        usage = self._usage.get(model_id, UsageRecord())
        
        return {
            "model_id": model_id,
            "requests": {
                "remaining": max(0, limits.rpd - usage.requests),
                "limit": limits.rpd,
                "used": usage.requests
            },
            "tokens": {
                "remaining": max(0, limits.tpd - usage.tokens),
                "limit": limits.tpd,
                "used": usage.tokens
            }
        }


# Tekil örnek (Singleton)
budget_tracker = BudgetTracker()
