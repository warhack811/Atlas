"""
Atlas Memory Write Gate (MWG)
------------------------------
FAZ 4: Merkezi hafıza yazma kararı motoru.

Bu modül, her triplet için "nereye yazılacak?" kararını verir:
- DISCARD: Hiçbir yere yazılmaz
- SESSION: Oturum hafızası (geçici, şimdilik Neo4j'ye yazılmaz)
- EPHEMERAL: TTL ile geçici (şimdilik Neo4j'ye yazılmaz)
- LONG_TERM: Kalıcı hafıza (Neo4j'ye yazılır)
- PROSPECTIVE: Gelecek task/reminder (Task node'a yazılır)

Karar Kuralları (MVP - Rule-based):
1. Policy.write_enabled=False => DISCARD (prospective hariç)
2. Catalog durability check (EPHEMERAL/SESSION/PROSPECTIVE fast path)
3. Scoring: utility + stability + confidence + recurrence
4. Threshold check => LONG_TERM veya EPHEMERAL
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, Optional
import re


class Decision(Enum):
    """MWG karar sonuçları."""
    DISCARD = "DISCARD"          # Hiçbir yere yazılmaz
    SESSION = "SESSION"           # Session memory (şimdilik Neo4j'ye yazılmaz)
    EPHEMERAL = "EPHEMERAL"       # TTL ile geçici (şimdilik Neo4j'ye yazılmaz)
    LONG_TERM = "LONG_TERM"       # Kalıcı hafıza (Neo4j'ye yazılır)
    PROSPECTIVE = "PROSPECTIVE"   # Gelecek task/reminder


@dataclass
class MWGResult:
    """
    MWG karar sonucu.
    
    Attributes:
        decision: Karar (DISCARD/SESSION/EPHEMERAL/LONG_TERM/PROSPECTIVE)
        ttl_seconds: TTL (sadece EPHEMERAL/SESSION için)
        reason: Karar gerekçesi (log/debug için)
        scores: Debug için scoring detayları
    """
    decision: Decision
    ttl_seconds: Optional[int]
    reason: str
    scores: Dict[str, float]


def is_prospective_intent(text: str) -> bool:
    """
    Mesajda prospective/reminder intent var mı kontrol et.
    
    Sinyal kelimeleri:
    - "hatırlat", "hatırla", "unutma", "remind"
    - Zaman ifadeleri: "yarın", "haftaya", "saat", "tarihi"
    
    Args:
        text: Orijinal kullanıcı mesajı
    
    Returns:
        True ise prospective intent mevcut
    
    MVP: Basit keyword matching. LLM kullanılmıyor (hız için).
    """
    PROSPECTIVE_KEYWORDS = [
        "hatırlat", "hatırla", "unutma", "remind", "reminder",
        "yarın", "haftaya", "gelecek", "sonra", "bugün",
        "saat", "dakika", "tarih"
    ]
    text_lower = text.lower()
    return any(kw in text_lower for kw in PROSPECTIVE_KEYWORDS)


def compute_utility_score(catalog, predicate_key: str, category: str) -> float:
    """
    Utility skoru: Bilginin faydalılığı (0.0-1.0).
    
    Yüksek utility:
    - Identity predicates (İSİM, YAŞI, MESLEĞİ)
    - Preferences (SEVER, SEVMİYOR)
    - Relationships (ARKADAŞI, EŞİ)
    
    Düşük utility:
    - Ephemeral state (NEREDE, HİSSEDİYOR)
    """
    pred_category = catalog.get_graph_category(predicate_key) if catalog else None
    
    # Category-based utility
    if pred_category == "identity":
        return 0.9
    elif pred_category == "preferences":
        return 0.8
    elif pred_category == "relationships":
        return 0.8
    elif pred_category == "events":
        return 0.7
    elif pred_category == "state":
        return 0.3  # Ephemeral state
    elif category == "personal":
        return 0.7
    else:
        return 0.5  # Default


def compute_stability_score(catalog, predicate_key: str) -> float:
    """
    Stability skoru: Bilginin istikrarı/değişmezliği (0.0-1.0).
    
    Yüksek stability:
    - STATIC predicates (İSİM, GELDİĞİ_YER)
    - LONG_TERM predicates (YAŞAR_YER, MESLEĞİ)
    
    Düşük stability:
    - EPHEMERAL predicates (NEREDE, HİSSEDİYOR)
    """
    durability = catalog.get_durability(predicate_key) if catalog else "LONG_TERM"
    
    if durability == "STATIC":
        return 1.0
    elif durability == "LONG_TERM":
        return 0.8
    elif durability == "SESSION":
        return 0.4
    elif durability == "EPHEMERAL":
        return 0.2
    else:
        return 0.6  # Default


async def compute_scores(triplet: Dict, catalog, predicate_key: str, user_id: str) -> Dict[str, float]:
    """
    Triplet için tüm skorları hesapla.
    
    Skorlar:
    - utility: 0.0-1.0 (faydalılık)
    - stability: 0.0-1.0 (istikrar)
    - confidence: 0.0-1.0 (güven)
    - recurrence: 0 veya 1 (tekrar)
    
    Args:
        triplet: subject-predicate-object dict
        catalog: PredicateCatalog instance
        predicate_key: Canonical predicate key
        user_id: Kullanıcı ID
    
    Returns:
        Skorlar dict'i
    """
    category = triplet.get("category", "general")
    confidence = triplet.get("confidence", 0.7)  # LLM confidence yoksa 0.7 varsay
    
    utility = compute_utility_score(catalog, predicate_key, category)
    stability = compute_stability_score(catalog, predicate_key)
    
    # Recurrence check (fact_exists helper ile)
    from atlas.memory.neo4j_manager import neo4j_manager
    subject = triplet.get("subject", "")
    predicate = catalog.get_canonical(predicate_key) if catalog else triplet.get("predicate", "")
    obj = triplet.get("object", "")
    
    recurrence = 0
    if subject and predicate and obj:
        exists = await neo4j_manager.fact_exists(user_id, subject, predicate, obj)
        recurrence = 1 if exists else 0
    
    return {
        "utility": utility,
        "stability": stability,
        "confidence": confidence,
        "recurrence": recurrence
    }


async def decide(
    triplet: Dict,
    policy,  # MemoryPolicy
    user_id: str,
    raw_text: str = ""
) -> MWGResult:
    """
    Bir triplet için MWG kararı ver (rule-based, LLM yok).
    
    Args:
        triplet: subject-predicate-object dict
        policy: MemoryPolicy instance
        user_id: Kullanıcı ID
        raw_text: Orijinal mesaj (intent detection için)
    
    Returns:
        MWGResult (decision, ttl, reason, scores)
    
    Karar Akışı:
    1. write_enabled kontrolü
    2. Catalog durability check (fast path)
    3. Scoring
    4. Threshold check
    5. Recurrence boost
    """
    from atlas.memory.predicate_catalog import get_catalog
    
    catalog = get_catalog()
    
    # 1. Write enabled kontrolü
    if not policy.write_enabled:
        # Prospective intent varsa izin ver
        if policy.prospective_enabled and is_prospective_intent(raw_text):
            return MWGResult(Decision.PROSPECTIVE, None, "write_enabled=False ama prospective intent var", {})
        return MWGResult(Decision.DISCARD, None, "write_enabled=False", {})
    
    # 2. Predicate catalog durability check
    predicate = triplet.get("predicate", "")
    predicate_key = catalog.resolve_predicate(predicate) if catalog else None
    
    if not predicate_key:
        return MWGResult(Decision.DISCARD, None, "Unknown predicate (catalog yok)", {})
    
    durability = catalog.get_durability(predicate_key) if catalog else "LONG_TERM"
    
    # Durability fast path
    if durability == "EPHEMERAL":
        ttl = policy.ttl_defaults.get("EPHEMERAL_SECONDS", 86400)
        return MWGResult(Decision.EPHEMERAL, ttl, f"Catalog durability=EPHEMERAL", {})
    
    if durability == "SESSION":
        ttl = policy.ttl_defaults.get("SESSION_SECONDS", 7200)
        return MWGResult(Decision.SESSION, ttl, f"Catalog durability=SESSION", {})
    
    if durability == "PROSPECTIVE":
        return MWGResult(Decision.PROSPECTIVE, None, "Catalog durability=PROSPECTIVE", {})
    
    # 3. Scoring (LONG_TERM adayları için)
    scores = await compute_scores(triplet, catalog, predicate_key, user_id)
    
    # 4. Threshold check
    th = policy.thresholds
    if (scores["utility"] >= th["utility"]
        and scores["stability"] >= th["stability"]
        and scores["confidence"] >= th["confidence"]):
        return MWGResult(
            Decision.LONG_TERM,
            None,
            f"Eşik üstü: U={scores['utility']:.2f}, S={scores['stability']:.2f}, C={scores['confidence']:.2f}",
            scores
        )
    
    # 5. Recurrence boost
    if scores.get("recurrence", 0) >= 1 and scores["utility"] >= th["utility"]:
        return MWGResult(Decision.LONG_TERM, None, "Recurrence pekiştirmesi (fact zaten var)", scores)
    
    # Default: EPHEMERAL
    ttl = policy.ttl_defaults.get("EPHEMERAL_SECONDS", 86400)
    return MWGResult(
        Decision.EPHEMERAL,
        ttl,
        f"Eşik altı: U={scores['utility']:.2f} < {th['utility']}, EPHEMERAL",
        scores
    )
