from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional

@dataclass
class ContextTrace:
    """
    Atlas Bağlam Üretim İzleme (Trace) Veri Yapısı.
    Bağlamın neden ve nasıl oluştuğunu açıklamak için kullanılır.
    """
    request_id: str
    user_id: str
    session_id: str
    intent: str = "UNKNOWN"
    memory_mode: str = "OFF"
    
    # Bütçe Dağılımı (Karakter cinsinden hedefler)
    budgets: Dict[str, int] = field(default_factory=lambda: {
        "transcript": 0,
        "episodic": 0,
        "semantic": 0,
        "total": 0
    })
    
    # Gerçek Kullanım (Karakter cinsinden)
    usage: Dict[str, int] = field(default_factory=lambda: {
        "transcript_chars": 0,
        "episode_chars": 0,
        "semantic_chars": 0,
        "total_chars": 0
    })
    
    # Seçilen Öğeler (ID listeleri)
    selected: Dict[str, List[str]] = field(default_factory=lambda: {
        "turn_ids": [],
        "episode_ids": [],
        "fact_ids": []
    })
    
    # RC-10: Skorlama Detayları (Explainability)
    scoring_details: Dict[str, Any] = field(default_factory=lambda: {
        "episodes": {} # ep_id -> scores
    })
    
    # Elenen Öğeler (Sayılar)
    filtered_counts: Dict[str, int] = field(default_factory=lambda: {
        "episode_filtered": 0,
        "semantic_filtered": 0,
        "deduped_lines": 0,
        "writes_skipped": 0 # RC-11: Negation/Uncertainty nedeniyle yazılmayanlar
    })
    
    # RC-11: İşlem Sayaçları
    metrics: Dict[str, int] = field(default_factory=lambda: {
        "corrections_applied_count": 0,
        "conflicts_detected_count": 0,
        "selected_facts_count": 0,
        "selected_signals_count": 0
    })
    
    # Karar Gerekçeleri
    reasons: List[str] = field(default_factory=list)
    
    # Zamanlama (ms)
    timings_ms: Dict[str, float] = field(default_factory=lambda: {
        "build_total_ms": 0.0,
        "fetch_turns_ms": 0.0,
        "fetch_episodes_ms": 0.0,
        "fetch_semantic_ms": 0.0,
        "dedupe_ms": 0.0
    })

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe sözlük dönüşümü."""
        return asdict(self)

    def add_reason(self, reason: str):
        """Yeni bir karar gerekçesi ekler."""
        if reason not in self.reasons:
            self.reasons.append(reason)
