"""
Atlas Memory Policy
-------------------
FAZ 4: Kullanıcı bazlı hafıza politika yönetimi.

Bu modül, her kullanıcı için hangi bilgilerin uzun dönem hafızaya (LTM) yazılacağını,
hangilerinin geçici (EPHEMERAL/SESSION) olacağını veya atılacağını kontrol eden
politika katmanıdır.

UI Bağlama Noktası:
- MemoryPolicy class'ı genişletilebilir (yeni alanlar eklenebilir)
- Neo4j User node'a memory_mode property eklenebilir
- Predicate bazlı override'lar UI'den yönetilebilir
"""

from dataclasses import dataclass, field
from typing import Dict, Optional
import os


@dataclass
class MemoryPolicy:
    """
    Kullanıcı bazlı hafıza politikası.
    
    Attributes:
        mode: Politika modu ("OFF" | "STANDARD" | "FULL")
        write_enabled: Uzun dönem hafıza yazımı aktif mi
        prospective_enabled: Gelecek hatırlatma/task'ler aktif mi
        thresholds: MWG karar eşikleri (0.0-1.0 arası)
        ttl_defaults: Geçici hafıza TTL değerleri (saniye)
        predicate_overrides: Predicate bazlı özel kurallar (UI'den ayarlanabilir)
    
    UI Bağlama Noktası:
        Bu class'a yeni alanlar eklenebilir (örn: max_facts_per_day, allowed_categories vb.)
        Değişiklikler geriye uyumlu olmalı (default değerler kullan)
    """
    mode: str = "STANDARD"  # OFF | STANDARD | FULL
    write_enabled: bool = True
    prospective_enabled: bool = True
    
    # MWG karar eşikleri (0.0-1.0 arası)
    # utility: Bilginin faydalılığı (identity/preferences yüksek)
    # stability: Bilginin istikrarı (identity yüksek, NEREDE düşük)
    # confidence: Bilgiye güven (0.0-1.0)
    # recurrence: Tekrarlanan bilgi (pekiştirme için)
    thresholds: Dict[str, float] = field(default_factory=lambda: {
        "utility": 0.6,
        "stability": 0.6,
        "confidence": 0.6,
        "recurrence": 1
    })
    
    # TTL varsayılanları (saniye)
    ttl_defaults: Dict[str, int] = field(default_factory=lambda: {
        "EPHEMERAL_SECONDS": 86400,  # 24 saat (günlük durum: yorgun, evde vb.)
        "SESSION_SECONDS": 7200       # 2 saat (geçici konuşma bağlamı)
    })
    
    # Predicate bazlı override'lar
    # Örnek: {"YAŞAR_YER": {"force_decision": "LONG_TERM", "ttl_seconds": None}}
    # UI bağlama noktası: Kullanıcı bazlı özel kurallar buradan yönetilebilir
    predicate_overrides: Dict[str, Dict] = field(default_factory=dict)


# Varsayılan politikalar
POLICY_OFF = MemoryPolicy(
    mode="OFF",
    write_enabled=False,
    prospective_enabled=True,  # Hatırlatmalar yine çalışabilir
    thresholds={
        "utility": 1.0,      # Çok yüksek eşik (hiçbir şey geçemez)
        "stability": 1.0,
        "confidence": 1.0,
        "recurrence": 1
    }
)

POLICY_STANDARD = MemoryPolicy(
    mode="STANDARD",
    write_enabled=True,
    prospective_enabled=True,
    thresholds={
        "utility": 0.6,      # Dengeli eşikler
        "stability": 0.6,
        "confidence": 0.6,
        "recurrence": 1
    }
)

POLICY_FULL = MemoryPolicy(
    mode="FULL",
    write_enabled=True,
    prospective_enabled=True,
    thresholds={
        "utility": 0.4,      # Daha düşük eşikler (daha geniş kapsam)
        "stability": 0.4,     # AMA EPHEMERAL durability'ler yine LTM'ye akmaz
        "confidence": 0.5,
        "recurrence": 1
    }
)


def get_default_policy(mode: str = "STANDARD") -> MemoryPolicy:
    """
    Belirtilen mod için varsayılan politika döndür.
    
    Args:
        mode: "OFF" | "STANDARD" | "FULL"
    
    Returns:
        MemoryPolicy instance
    
    Örnek:
        >>> policy = get_default_policy("FULL")
        >>> policy.thresholds["utility"]
        0.4
    """
    policies = {
        "OFF": POLICY_OFF,
        "STANDARD": POLICY_STANDARD,
        "FULL": POLICY_FULL
    }
    return policies.get(mode.upper(), POLICY_STANDARD)


async def load_policy_for_user(user_id: str) -> MemoryPolicy:
    """
    Kullanıcı için politika yükle.
    
    Öncelik sırası:
    1. Neo4j User node memory_mode property (UI bağlama noktası)
    2. Environment variable ATLAS_DEFAULT_MEMORY_MODE
    3. Varsayılan: STANDARD
    
    Args:
        user_id: Kullanıcı kimliği
    
    Returns:
        Kullanıcıya özel MemoryPolicy
    
    UI Bağlama Noktası:
        Neo4j'ye User node'a memory_mode property eklenebilir:
        MATCH (u:User {id: $uid}) SET u.memory_mode = 'FULL'
    """
    try:
        from Atlas.memory.neo4j_manager import neo4j_manager
        mode = await neo4j_manager.get_user_memory_mode(user_id)
        if mode:
            return get_default_policy(mode)
    except Exception:
        # Fallback if Neo4j is unavailable
        pass
    
    # Fallback: Environment variable + default
    mode = os.getenv("ATLAS_DEFAULT_MEMORY_MODE", "STANDARD")
    return get_default_policy(mode)
