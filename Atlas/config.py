"""
ATLAS Yönlendirici - Merkezi Yapılandırma (Central Configuration)
----------------------------------------------------------------
Bu modül, tüm sistemin çalışma parametrelerini, API anahtarlarını, model
yönetişim kurallarını ve davranış ayarlarını tek bir noktadan yönetir.

Temel Sorumluluklar:
1. Ortam Değişkenleri: .env dosyasından anahtar ve URL bilgilerini yükleme.
2. Model Yönetişimi (Governance): Hangi görev için hangi birincil ve yedek modellerin kullanılacağını tanımlama.
3. API Ayarları: Zaman aşımı, temperature (yaratıcılık) ve token limitlerini belirleme.
4. Davranış Haritalama: Niyet (intent) ve tarza (style) göre model ayarlarını optimize etme.
"""
import os
from os import getenv
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()

class Config:
    """Merkezi konfigürasyon yönetimi."""
    SERPER_API_KEY = getenv("SERPER_API_KEY", "")
    FLUX_API_URL = getenv("FLUX_API_URL", "http://localhost:7860/sdapi/v1/txt2img") # Varsayılan Forge/A1111 URL
    ATLAS_SESSION_SECRET = getenv("ATLAS_SESSION_SECRET", None)
    
    # Neo4j Ayarları
    NEO4J_URI = getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER = getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD = getenv("NEO4J_PASSWORD", "password")

    # Mevcut anahtarlar (Backward compatibility için)
    
    # Mevcut anahtarlar (Backward compatibility için)
    GEMINI_API_KEY = getenv("GEMINI_API_KEY", "")

    @classmethod
    def get_random_groq_key(cls) -> str:
        """Groq API anahtarları arasından rastgele birini seçer."""
        import random
        keys = get_groq_api_keys()
        return random.choice(keys) if keys else ""

def get_groq_api_keys() -> list[str]:
    """Sistem yapılandırmasından veya ortam değişkenlerinden Groq API anahtarlarını çeker."""
    import os
    # Ortam değişkenlerinden çek
    keys = [
        getenv("GROQ_API_KEY", ""),
        getenv("GROQ_API_KEY_BACKUP", ""),
        getenv("GROQ_API_KEY_3", ""),
        getenv("GROQ_API_KEY_4", ""),
    ]
    return [k for k in keys if k]


def get_gemini_api_keys() -> list[str]:
    """Ortam değişkenlerinden yüklü olan Gemini (Google) API anahtarlarını getirir."""
    import os
    keys = [
        getenv("GEMINI_API_KEY", ""),
        getenv("GEMINI_API_KEY_2", ""),
        getenv("GEMINI_API_KEY_3", ""),
    ]
    return [k for k in keys if k]


def get_gemini_api_key() -> str:
    """Birincil Gemini API anahtarını döner (Geriye dönük uyumluluk için)."""
    keys = get_gemini_api_keys()
    return keys[0] if keys else ""



# --- MODEL YÖNETİŞİM (GOVERNANCE) ---
# Her rol için: [Birincil, Alternatif 1, Alternatif 2]
MODEL_GOVERNANCE = {
    "orchestrator": [
        "gemini-2.0-flash",
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant"
    ],
    "safety": [
        "meta-llama/llama-prompt-guard-2-86m",
        "meta-llama/llama-guard-4-12b",
        "openai/gpt-oss-safeguard-20b"
    ],
    "coding": [
        "openai/gpt-oss-120b",
        "llama-3.3-70b-versatile",
        "qwen/qwen3-32b"
    ],
    "tr_creative": [
        "moonshotai/kimi-k2-instruct",
        "moonshotai/kimi-k2-instruct-0905",
        "llama-3.3-70b-versatile",
        "qwen/qwen3-32b"
    ],
    "logic": [
        "llama-3.3-70b-versatile",
        "moonshotai/kimi-k2-instruct",
        "moonshotai/kimi-k2-instruct-0905",
        "meta-llama/llama-4-maverick-17b-128e-instruct",
        "openai/gpt-oss-20b"
    ],
    "search": [
        "llama-3.3-70b-versatile",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "llama-3.1-8b-instant"
    ],
    "synthesizer": [
        "moonshotai/kimi-k2-instruct-0905",
        "moonshotai/kimi-k2-instruct",
        "llama-3.3-70b-versatile",
        "openai/gpt-oss-120b"     
    ],
    "episodic_summary": [
        "gemini-2.0-flash",
        "llama-3.3-70b-versatile"
    ]
}

# --- CONTEXT QUALITY & BUDGET (RC-5/RC-8) ---
CONTEXT_BUDGET = {
    "max_total_chars": 6000,
    "weights": {
        "transcript": 0.4,   # max 2400 chars
        "episodic": 0.3,     # max 1800 chars
        "semantic": 0.3      # max 1800 chars
    }
}

# RC-10: Anlamsal Benzerlik (Semantic Similarity) Ayarları
EMBEDDING_SETTINGS = {
    "PROVIDER": getenv("EMBEDDER_PROVIDER", "hash"), # 'hash' veya 'sentence-transformers'
    "MODEL_NAME": "all-MiniLM-L6-v2",
    "DIMENSION": 384,
    "SCORING_WEIGHTS": {
        "overlap": 0.45,
        "semantic": 0.35,
        "recency": 0.20
    }
}

# RC-8: Niyete göre dinamik bütçe profilleri
CONTEXT_BUDGET_PROFILES = {
    "GENERAL":   {"transcript": 0.80, "episodic": 0.20, "semantic": 0.00},
    "FOLLOWUP":  {"transcript": 0.60, "episodic": 0.25, "semantic": 0.15},
    "PERSONAL":  {"transcript": 0.30, "episodic": 0.20, "semantic": 0.50},
    "TASK":      {"transcript": 0.35, "episodic": 0.25, "semantic": 0.40},
    "MIXED":     {"transcript": 0.40, "episodic": 0.30, "semantic": 0.30},
}


# RC-11: Confidence & Decay Ayarları
MEMORY_CONFIDENCE_SETTINGS = {
    "DEFAULT_HARD_FACT_CONFIDENCE": 1.0,
    "DEFAULT_SOFT_SIGNAL_CONFIDENCE": 0.6,
    "UNCERTAINTY_THRESHOLD": 0.5, # Bu altındaki veriler SOFT_SIGNAL veya OPEN_QUESTION olur
    "DECAY_RATE_PER_DAY": 0.05,    # Gün başına düşecek confidence (Soft signallar için)
    "CONFLICT_THRESHOLD": 0.7,     # İki veri arasındaki çelişkiyi raporlama sınırı
    "DROP_THRESHOLD": 0.4,         # Bu değerin altındaki tüm çıkarımları çöpe at (Discard)
    "SOFT_SIGNAL_THRESHOLD": 0.7   # SOFT_SIGNAL'a düşürme sınırı
}

# --- OPS & SAFETY (RC-8 Pilot) ---
DEBUG = False  # Admin endpointları için (Purge vb.)
BYPASS_MEMORY_INJECTION = False  # True ise semantic+episodic kapalı
BYPASS_ADAPTIVE_BUDGET = False   # True ise intent profilleri kapalı (standard profile)

# --- ACCESS CONTROL (INTERNAL_ONLY Mode) ---
# True ise sadece whitelist'teki user_id'ler erişebilir, diğerleri 403 alır
INTERNAL_ONLY = getenv("INTERNAL_ONLY", "false").lower() == "true"

# Virgülle ayrılmış whitelist user_id'leri (env'den veya varsayılanlar)
# Örnek: INTERNAL_WHITELIST_USER_IDS="u_admin123,u_dev456,u_test789"
_whitelist_raw = getenv("INTERNAL_WHITELIST_USER_IDS", "")
INTERNAL_WHITELIST_USER_IDS: set[str] = set(
    uid.strip() for uid in _whitelist_raw.split(",") if uid.strip()
)

# Startup log for debugging
import logging as _logging
_config_logger = _logging.getLogger("config")
_config_logger.info(f"[CONFIG] INTERNAL_ONLY={INTERNAL_ONLY}, WHITELIST={INTERNAL_WHITELIST_USER_IDS or '(empty)'}")

def is_user_whitelisted(user_id: str) -> bool:
    """
    INTERNAL_ONLY modunda kullanıcının erişim yetkisi var mı kontrol eder.
    
    Returns:
        True: INTERNAL_ONLY kapalı VEYA user_id whitelist'te
        False: INTERNAL_ONLY açık VE user_id whitelist'te değil
    """
    if not INTERNAL_ONLY:
        return True  # Açık erişim
    
    is_allowed = user_id in INTERNAL_WHITELIST_USER_IDS
    if not is_allowed:
        _config_logger.warning(
            f"[ACCESS_DENIED] INTERNAL_ONLY=true, user_id='{user_id}', "
            f"whitelist={list(INTERNAL_WHITELIST_USER_IDS)}"
        )
    return is_allowed

# --- RETENTION & FORGETFULNESS (RC-6) ---
RETENTION_SETTINGS = {
    "TURN_RETENTION_DAYS": 30,
    "MAX_TURNS_PER_SESSION": 400,
    "EPISODE_RETENTION_DAYS": 180,
    "NOTIFICATION_RETENTION_DAYS": 30,
    "DONE_TASK_RETENTION_DAYS": 30
}

CONSOLIDATION_SETTINGS = {
    "ENABLE_CONSOLIDATION": True,
    "CONSOLIDATION_EPISODE_WINDOW": 10,  # 10 REGULAR -> 1 CONSOLIDATED
    "CONSOLIDATION_MIN_AGE_DAYS": 7      # 7 günden eski olanlar
}

# Time & Context Awareness
URGENCY_KEYWORDS = ["acil", "hemen", "urgent", "asap", "deadline", "yarın", "bugün", "şimdi"]

# Arena Category-Specific Temperatures (Optimized per task type)
ARENA_CATEGORY_TEMPERATURE = {
    "coding": 0.3,        # Lower = more deterministic for code accuracy
    "math": 0.2,          # Very low for precision
    "reasoning": 0.4,     # Moderate for logical consistency
    "creative": 0.8,      # Higher for diverse creative outputs
    "roleplay": 0.7,      # High for natural conversation
    "tr_quality": 0.5,    # Balanced for language quality
    "security": 0.3,      # Low for consistent secure patterns
    "general": 0.5        # Default fallback
}


# API Settings
API_CONFIG = {
    "groq_api_base": "https://api.groq.com/openai/v1",
    "default_temperature": 0.7,
    "max_tokens": 2048,
    "frequency_penalty": 0.1,
    "presence_penalty": 0.1
}

# Style Profile → Temperature Mapping (Optimized for persona consistency)
STYLE_TEMPERATURE_MAP = {
    "professional": 0.3,
    "expert": 0.3,
    "friendly": 0.5,
    "standard": 0.5,
    "kanka": 0.8,
    "creative": 0.8,
    "teacher": 0.4,
    "girlfriend": 0.8,
    "sincere": 0.6,
    "concise": 0.3,
    "detailed": 0.5,
    "default": 0.5
}

# Niyet (Intent) başına Temperature Eşleşmesi
# Not: Düşük değerler daha tutarlı/teknik, yüksek değerler daha yaratıcı çıktı sağlar.
INTENT_TEMPERATURE = {
    # Kesin/teknik görevler → düşük temperature
    "coding": 0.3,
    "debug": 0.2,
    "refactor": 0.3,
    "math": 0.2,
    "calculation": 0.2,
    "analysis": 0.4,
    "comparison": 0.4,
    
    # Yaratıcı görevler → yüksek temperature
    "creative": 0.8,
    "story": 0.85,
    "poem": 0.9,
    "roleplay": 0.8,
    
    # Genel/sohbet → orta temperature
    "greeting": 0.6,
    "question": 0.5,
    "general": 0.5,
    "search": 0.5,
}
