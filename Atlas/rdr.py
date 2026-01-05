"""
ATLAS Yönlendirici - Yönlendirme Karar Kaydı (Routing Decision Record - RDR)
---------------------------------------------------------------------------
Bu bileşen, sisteme gelen her bir isteğin yaşam döngüsünü en ince ayrıntısına
kadar kayıt altına alır. Hata ayıklama (debug), performans analizi ve 
şeffaflık (traceability) için kritik öneme sahiptir.

Kaydedilen Bilgiler:
1. Temel Bilgiler: İstek ID, zaman damgası, orijinal ve işlenmiş mesaj.
2. Karar Mekanizması: Niyet sınıflandırması, model seçimi ve seçilme nedenleri.
3. Performans Verileri: Güvenlik, sınıflandırma, yürütme ve sentez aşamalarının süreleri.
4. Güvenlik ve Kalite: Güvenlik süzgecinden geçiş durumu ve tespit edilen kalite sorunları.
5. Görev Detayları: Çoklu görevlerin (multi-task) durumu, kullanılan uzman modeller.
6. Bağlam ve Stil: Enjekte edilen hafıza verileri, kullanılan persona ve tonlama.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional
import uuid
import json


@dataclass
class RDR:
    """Sistemdeki her bir işlemin 'kara kutu' kaydını tutan veri sınıfı."""
    
    # Kimlik ve Zaman
    request_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Girdi Verileri
    message: str = ""
    message_length: int = 0
    rewritten_query: str = ""
    
    # Niyet Sınıflandırma
    intent: str = "unknown"
    confidence: float = 0.0
    tier_used: int = -1
    cascade_path: list = field(default_factory=list)
    
    # Model Seçimi
    model_category: str = ""
    model_id: str = ""
    model_reason: str = ""
    
    # Performans Gözetimi (milisaniye cinsinden)
    safety_ms: int = 0
    classification_ms: int = 0
    dag_execution_ms: int = 0
    synthesis_ms: int = 0
    quality_ms: int = 0
    total_ms: int = 0
    generation_ms: int = 0 # Deprecated, keeping for compatibility
    
    # Yanıt Özellikleri
    response_length: int = 0
    response_preview: str = ""
    
    # Güvenlik Katmanı (Faz 7)
    safety_passed: bool = True
    safety_issues: list = field(default_factory=list)  # [{"type": "PII", "details": "..."}]
    pii_redacted: bool = False
    injection_blocked: bool = False
    
    # Kalite Kapıları (Faz 8)
    quality_passed: bool = True
    quality_issues: list = field(default_factory=list)  # [{"check": "LENGTH", "severity": "WARNING"}]
    
    # Bütçe Takibi (Faz 9)
    budget_remaining_pct: float = 100.0  # Kalan bütçe yüzdesi
    budget_alerts: list = field(default_factory=list)  # [{"level": "WARNING", "metric": "requests"}]
    tokens_used: int = 0
    
    is_multi_task: bool = False
    tasks_count: int = 1
    tasks_completed: int = 0
    tasks_failed: int = 0
    parallel_groups_count: int = 0
    task_details: list = field(default_factory=list)  # [{"task_id": "...", "model": "...", "status": "..."}]
    
    # Fallback Chain (Faz 11)
    fallback_used: bool = False
    fallback_attempts: int = 0
    fallback_models: list = field(default_factory=list)  # ["model1", "model2", ...]
    quality_degraded: bool = False
    degradation_reason: str = ""
    
    # Style Injection (Faz 12)
    style_used: bool = False
    style_persona: str = ""
    style_tone: str = ""
    style_preset: str = ""
    
    # Zaman ve Kullanıcı Bağlamı
    time_context: str = ""
    user_facts_dump: list = field(default_factory=list)
    full_context_injection: str = ""
    
    # Teknik Yürütme Detayları
    task_details: list = field(default_factory=list)
    raw_expert_responses: list = field(default_factory=list) # [{"model": "...", "response": "..."}]
    synthesizer_model: str = ""
    
    is_urgent: bool = False
    urgency_keywords: list = field(default_factory=list)
    
    # Enjekte edilen ham istemler
    orchestrator_prompt: str = ""
    synthesizer_prompt: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    @classmethod
    def create(cls, message: str) -> "RDR":
        """Belirli bir mesaj için başlangıç verileriyle yeni bir RDR kaydı oluşturur."""
        return cls(
            message=message,
            message_length=len(message)
        )


# Test için bellek içi depolama
_rdr_storage: dict[str, RDR] = {}
_RDR_MAX_SIZE = 1000  # Maksimum kayıt sayısı


def save_rdr(rdr: RDR) -> None:
    """RDR'yi depolamaya kaydet (FIFO eviction)."""
    global _rdr_storage
    
    # Max-size kontrolü - eski kayıtları sil
    if len(_rdr_storage) >= _RDR_MAX_SIZE:
        # En eski kaydı bul ve sil
        oldest_id = min(_rdr_storage.keys(), key=lambda k: _rdr_storage[k].timestamp)
        del _rdr_storage[oldest_id]
    
    _rdr_storage[rdr.request_id] = rdr


def get_rdr(request_id: str) -> Optional[RDR]:
    """Request ID ile RDR getir."""
    return _rdr_storage.get(request_id)


def get_recent_rdrs(limit: int = 10) -> list[RDR]:
    """En son RDR'leri getir."""
    sorted_rdrs = sorted(
        _rdr_storage.values(),
        key=lambda r: r.timestamp,
        reverse=True
    )
    return sorted_rdrs[:limit]
