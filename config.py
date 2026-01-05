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
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()

class Config:
    """Merkezi konfigürasyon yönetimi."""
    SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
    FLUX_API_URL = os.getenv("FLUX_API_URL", "http://localhost:7860/sdapi/v1/txt2img") # Varsayılan Forge/A1111 URL
    
    # Neo4j Ayarları
    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
    
    # Mevcut anahtarlar (Backward compatibility için)
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

    @classmethod
    def get_random_groq_key(cls) -> str:
        """Groq API anahtarları arasından rastgele birini seçer."""
        import random
        keys = get_groq_api_keys()
        return random.choice(keys) if keys else ""

def get_groq_api_keys() -> list[str]:
    """Sistem yapılandırmasından veya ortam değişkenlerinden Groq API anahtarlarını çeker."""
    try:
        from app.config import get_settings
        settings = get_settings()
        return settings.get_groq_api_keys()
    except ImportError:
        import os
        # Hata durumunda doğrudan ortam değişkenlerinden çekmeyi dene
        keys = [
            os.getenv("GROQ_API_KEY", ""),
            os.getenv("GROQ_API_KEY_BACKUP", ""),
            os.getenv("GROQ_API_KEY_3", ""),
            os.getenv("GROQ_API_KEY_4", ""),
        ]
        return [k for k in keys if k]


def get_gemini_api_keys() -> list[str]:
    """Ortam değişkenlerinden yüklü olan Gemini (Google) API anahtarlarını getirir."""
    import os
    keys = [
        os.getenv("GEMINI_API_KEY", ""),
        os.getenv("GEMINI_API_KEY_2", ""),
        os.getenv("GEMINI_API_KEY_3", ""),
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
        "meta-llama/llama-guard-4-12b",
        "meta-llama/llama-prompt-guard-2-86m",
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
    ]
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
