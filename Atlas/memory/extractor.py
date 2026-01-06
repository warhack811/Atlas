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
from Atlas.config import Config, API_CONFIG
from Atlas.prompts import EXTRACTOR_SYSTEM_PROMPT
from Atlas.memory.neo4j_manager import neo4j_manager
from Atlas.memory.predicate_catalog import get_catalog

logger = logging.getLogger(__name__)

# Bilgi çıkarımı için kullanılacak model
EXTRACTION_MODEL = "llama-3.3-70b-versatile"

# Faz 1: Pronoun/placeholder filter (geçici, Faz 3'e kadar)
# Ben/Sen/O gibi zamirleri subject/object olarak kabul etme
# Neo4j zaten title/upper yapıyor, burada hem raw hem normalized kontrol et
PRONOUN_FILTER = {
    "BEN", "SEN", "BIZ", "SİZ", "O", "ONLAR", 
    "HOCAM", "HOCA", "KENDIM", "KENDİM", "BANA", "SANA",
    # Normalized versions (Turkish -> ASCII)
    "SIZ", "KENDIM"
}

def sanitize_triplets(triplets: List[Dict], user_id: str, raw_text: str) -> List[Dict]:
    """
    Faz 1: Triplets post-processor - enforces predicate catalog rules.
    
    Filters:
    1. Required fields check (subject, predicate, object)
    2. Pronoun filter (BEN/SEN/O etc.)
    3. Predicate canonicalization (alias → canonical)
    4. Unknown predicate drop (fail-closed if catalog exists)
    5. Disabled predicate drop
    6. Category bridge (catalog → personal/general)
    7. Durability filter (EPHEMERAL/SESSION predicates dropped)
    
    Returns:
        Filtered list of triplets ready for Neo4j
    """
    catalog = get_catalog()
    
    # Fail-open: if catalog failed to load, pass through without filtering
    if catalog is None:
        logger.warning(f"CATALOG_DISABLED: Passing {len(triplets)} triplets without filtering")
        return triplets
    
    cleaned = []
    
    for triplet in triplets:
        # 1. Required fields
        subject = triplet.get("subject", "").strip()
        predicate = triplet.get("predicate", "").strip()
        obj = triplet.get("object", "").strip()
        
        if not subject or not predicate or not obj:
            logger.debug(f"DROP: Missing required field - {triplet}")
            continue
        
        # Drop single-character entities
        if len(subject) < 2 or len(obj) < 2:
            logger.debug(f"DROP: Too short - subject='{subject}', object='{obj}'")
            continue
        
        # 2. Pronoun filter
        subject_upper = subject.upper()
        obj_upper = obj.upper()
        
        if subject_upper in PRONOUN_FILTER or obj_upper in PRONOUN_FILTER:
            logger.info(f"PRONOUN_DROPPED: '{subject}' - '{predicate}' - '{obj}'")
            continue
        
        # 3. Predicate canonicalization
        raw_predicate = predicate
        predicate_key = catalog.resolve_predicate(raw_predicate)
        
        if predicate_key is None:
            logger.info(f"UNKNOWN_PREDICATE_DROPPED: '{raw_predicate}' in triplet: {subject} - {obj}")
            continue
        
        # 4. Enabled check
        if not catalog.get_enabled(predicate_key):
            logger.info(f"DISABLED_PREDICATE_DROPPED: '{raw_predicate}' (key={predicate_key})")
            continue
        
        # 5. Get canonical form
        canonical = catalog.get_canonical(predicate_key)
        
        # 6. Durability filter (Faz 1 minimal MWG)
        durability = catalog.get_durability(predicate_key)
        if durability in {"EPHEMERAL", "SESSION"}:
            logger.info(f"EPHEMERAL_DROPPED: '{canonical}' (durability={durability})")
            continue
        
        # 7. Category bridge
        graph_category = catalog.get_graph_category(predicate_key)
        
        # Build cleaned triplet
        cleaned.append({
            "subject": subject,
            "predicate": canonical,  # Use canonical form
            "object": obj,
            "category": graph_category  # Override with catalog category
        })
    
    if len(cleaned) < len(triplets):
        logger.info(f"FAZ1_FILTER: {len(triplets)} → {len(cleaned)} triplets (dropped {len(triplets) - len(cleaned)})")
    
    return cleaned


async def extract_and_save(text: str, user_id: str, source_turn_id: str | None = None):
    """
    Belirli bir metinden anlamlı bilgileri çıkarır ve veritabanına kaydeder.
    
    Args:
        text: Analiz edilecek kullanıcı mesajı
        user_id: Kullanıcı kimliği (session_id)
        source_turn_id: Bu bilginin geldiği konuşma turn'ünün ID'si (RDR request_id) - FAZ2 provenance
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
                # FAZ1-2: Apply predicate catalog enforcement before Neo4j write
                cleaned_triplets = sanitize_triplets(triplets, user_id, text)
                
                if cleaned_triplets:
                    # FAZ2: source_turn_id provenance bilgisi ile Neo4j'ye kaydet
                    logger.info(f"Neo4j'ye kaydediliyor: {len(cleaned_triplets)} triplet (cleaned from {len(triplets)})")
                    await neo4j_manager.store_triplets(cleaned_triplets, user_id, source_turn_id)
                    return cleaned_triplets
                else:
                    logger.info("Tüm triplet'ler Faz 1 filtreleri tarafından drop edildi.")
                    return []
            else:
                logger.info("Mesajdan anlamlı bir bilgi çıkarılmadı.")
                return []

    except Exception as e:
        logger.error(f"extract_and_save metodunda hata: {str(e)}")
        return []
