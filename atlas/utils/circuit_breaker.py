"""
ATLAS Yönlendirici - Devre Kesici (Circuit Breaker v2)
-----------------------------------------------------
Bu bileşen, dış servislerde (API'ler) meydana gelen ardışık hataları takip eder.
Hatalar belirli bir eşiği aştığında, sistemi korumak ve gereksiz beklemeleri
önlemek için akışı otomatik olarak keser (fail-fast).

Durumlar:
- CLOSED (KAPALI): Her şey normal, istekler servis sağlayıcıya iletilir.
- OPEN (AÇIK): Hata eşiği aşıldı, istekler anında reddedilir (koruma modu).
- HALF-OPEN (YARI-AÇIK): Bekleme süresi doldu, sistemin düzelip düzelmediğini
  test etmek için sınırlı sayıda isteğe izin verilir.
"""

import time
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Callable


class CircuitState(Enum):
    """Devre kesicinin alabileceği durum değerleri."""
    CLOSED = "closed"        # Normal çalışma
    OPEN = "open"            # Hata modu (İletişim kesildi)
    HALF_OPEN = "half_open"  # Test modu


@dataclass
class CircuitStats:
    """Hata ve başarı istatistiklerini tutan veri sınıfı."""
    fail_count: int = 0
    success_count: int = 0
    total_calls: int = 0
    last_failure_time: Optional[float] = None
    last_state_change: float = time.time()
    state: CircuitState = CircuitState.CLOSED


class CircuitBreaker:
    """Dış servis çağrılarını denetleyen ve hata durumunda devreyi kesen sınıf."""
    
    def __init__(self, service_name: str, fail_threshold: int = 5, reset_timeout: int = 60):
        self.service_name = service_name
        self.fail_threshold = fail_threshold
        self.reset_timeout = reset_timeout
        self.stats = CircuitStats()
    
    def can_execute(self) -> bool:
        """İstek yapılabilir mi?"""
        if self.stats.state == CircuitState.CLOSED:
            return True
        
        if self.stats.state == CircuitState.OPEN:
            # Timeout kontrolü
            if time.time() - self.stats.last_state_change > self.reset_timeout:
                self._transition_to(CircuitState.HALF_OPEN)
                return True
            return False
            
        if self.stats.state == CircuitState.HALF_OPEN:
            # Half-open'da sadece 1 isteğe izin ver (basit implementasyon)
            # Gerçekte semaphore/lock kullanılabilir
            return True
            
        return False
    
    def record_success(self):
        """Başarılı çağrı kaydı."""
        self.stats.total_calls += 1
        self.stats.success_count += 1
        
        if self.stats.state == CircuitState.HALF_OPEN:
            self._transition_to(CircuitState.CLOSED)
            self.stats.fail_count = 0
    
    def record_failure(self):
        """Hatalı çağrı kaydı."""
        self.stats.total_calls += 1
        self.stats.fail_count += 1
        self.stats.last_failure_time = time.time()
        
        if self.stats.state == CircuitState.HALF_OPEN:
            self._transition_to(CircuitState.OPEN)
        
        elif self.stats.state == CircuitState.CLOSED:
            if self.stats.fail_count >= self.fail_threshold:
                self._transition_to(CircuitState.OPEN)
                
    def _transition_to(self, new_state: CircuitState):
        """Durum değişikliği."""
        print(f"[Şalter] {self.service_name}: {self.stats.state.value} -> {new_state.value}")
        self.stats.state = new_state
        self.stats.last_state_change = time.time()
        
    def get_status(self) -> dict:
        """Sistem sağlığı API'si için güncel durum özeti döner."""
        return {
            "service": self.service_name,
            "state": self.stats.state.value,
            "fail_count": self.stats.fail_count,
            "success_count": self.stats.success_count,
            "is_open": self.stats.state == CircuitState.OPEN
        }


# Şalter Yöneticisi (Singleton)
class CircuitManager:
    """Tüm servis şalterlerini merkezi bir noktadan yöneten sınıf."""
    _circuits: dict[str, CircuitBreaker] = {}
    
    @classmethod
    def get_breaker(cls, service_name: str) -> CircuitBreaker:
        if service_name not in cls._circuits:
            cls._circuits[service_name] = CircuitBreaker(service_name)
        return cls._circuits[service_name]
    
    @classmethod
    def get_all_status(cls) -> list[dict]:
        return [cb.get_status() for cb in cls._circuits.values()]
