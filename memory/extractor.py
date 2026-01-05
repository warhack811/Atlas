"""
ATLAS Yönlendirici - Bilgi Çıkarım Motoru (Information Extractor)
-----------------------------------------------------------------
Bu bileşen, kullanıcı mesajlarını analiz ederek uzun vadeli hafızaya (Neo4j)
kaydedilecek önemli bilgileri özne-yüklem-nesne (triplet) yapısında çıkarır.

Temel Sorumluluklar:
1. Bilgi Tespiti: Mesajdaki kalıcı gerçekleri (isim, konum, tercihler vb.) ayıklama.
2. Formata Dönüştürme: Doğal dili, graf veritabanının anlayacağı JSON formatına çevirme.
3. Otomatik Kayıt: Çıkarılan bilgileri Neo4jManager aracılığıyla veritabanına işleme.
4. Filtreleme: Geçici durumları ve anlamsız verileri eleyerek hafıza kirliliğini önleme.
"""
import json
import httpx
import logging
from typing import List, Dict, Any
from ..config import Config, API_CONFIG
from ..prompts import EXTRACTOR_SYSTEM_PROMPT
from .neo4j_manager import neo4j_manager

logger = logging.getLogger(__name__)

# Bilgi çıkarımı için kullanılacak model
EXTRACTION_MODEL = "llama-3.3-70b-versatile"

async def extract_and_save(text: str, user_id: str):
    """
    Belirli bir metinden anlamlı bilgileri çıkarır ve veritabanına kaydeder.
    """
    if not text or len(text.strip()) < 5:
        return []

    # Groq API üzerinden model çağrısı için rastgele bir anahtar seç
    api_key = Config.get_random_groq_key()
    if not api_key:
        logger.error("Groq API anahtarı bulunamadı. Bilgi çıkarımı atlanıyor.")
        return []

    url = f"{API_CONFIG['groq_api_base']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": EXTRACTION_MODEL,
        "messages": [
            {"role": "system", "content": EXTRACTOR_SYSTEM_PROMPT},
            {"role": "user", "content": text}
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"} if "llama-3.3" in EXTRACTION_MODEL else None
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            
            # Modelden gelen JSON metnini Python listesine/objesine dönüştür
            parsed = json.loads(content)
            
            # Farklı olası JSON yapılarını (liste veya dict) normalize et
            triplets = []
            if isinstance(parsed, list):
                triplets = parsed
            elif isinstance(parsed, dict):
                # Model bazen {"triplets": [...]} şeklinde dönebilir
                triplets = parsed.get("triplets", parsed.get("facts", parsed.get("items", [])))
                if not triplets and len(parsed) > 0 and not any(isinstance(v, (list, dict)) for v in parsed.values()):
                    # Eğer doğrudan alanlar varsa (örn: {"subject": "...", ...})
                    if "subject" in parsed and "predicate" in parsed:
                        triplets = [parsed]

            if triplets:
                logger.info(f"Metinden {len(triplets)} adet bilgi (triplet) çıkarıldı. Neo4j'ye kaydediliyor...")
                await neo4j_manager.store_triplets(triplets, user_id)
                return triplets
            else:
                logger.info("Mesajdan anlamlı bir bilgi çıkarılmadı.")
                return []

    except Exception as e:
        logger.error(f"extract_and_save metodunda hata: {str(e)}")
        return []
