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
from atlas.config import Config, API_CONFIG, MEMORY_CONFIDENCE_SETTINGS
from atlas.utils.resource_loader import ResourceLoader
EXTRACTOR_SYSTEM_PROMPT = ResourceLoader.get_prompt("extractor_system_prompt")
from atlas.memory.neo4j_manager import neo4j_manager
from atlas.memory.predicate_catalog import get_catalog

logger = logging.getLogger(__name__)

# Bilgi çıkarımı için kullanılacak model
EXTRACTION_MODEL = "llama-3.3-70b-versatile"

# FAZ 3: Pronoun handling artık identity_resolver modülünde yapılıyor
# PRONOUN_FILTER kaldırıldı - is_first_person, is_second_person, is_other_pronoun kullan


def sanitize_triplets(triplets: List[Dict], user_id: str, raw_text: str, known_names: List[str] = None) -> List[Dict]:
    """
    Faz 1: Triplets post-processor - enforces predicate catalog rules.
    Faz 3: 1. şahıs zamirlerini (BEN/BENIM) user anchor'a map eder.
    FAZ-γ: Bilinen kullanıcı isimlerini anchor'a map eder.
    
    Filters:
    1. Required fields check (subject, predicate, object)
    2. First-person subject mapping (BEN → __USER__::<user_id>) - FAZ3
    3. Pronoun filter (SEN/O/ONLAR etc. still dropped)
    4. Predicate canonicalization (alias → canonical)
    5. Unknown predicate drop (fail-closed if catalog exists)
    6. Disabled predicate drop
    7. Category bridge (catalog → personal/general)
    8. Durability filter (EPHEMERAL/SESSION predicates dropped)
    
    Returns:
        Filtered list of triplets ready for Neo4j
    """
    # FAZ3: Identity resolver modülünü import et
    from atlas.memory.identity_resolver import (
        is_first_person, is_second_person, is_other_pronoun, get_user_anchor
    )
    
    catalog = get_catalog()
    
    # Fail-open: if catalog failed to load, pass through without filtering
    if catalog is None:
        logger.warning(f"CATALOG_DISABLED: Passing {len(triplets)} triplets without filtering")
        return triplets
    
    cleaned = []
    
    # RC-11: Thresholds from central config
    settings = MEMORY_CONFIDENCE_SETTINGS
    threshold = settings.get("UNCERTAINTY_THRESHOLD", 0.5)
    
    for triplet in triplets:
        # Professional Null-Coalescing to prevent NoneType.strip()
        # triplet.get(x, "") only works if key is missing. If key is None, it returns None.
        subject = str(triplet.get("subject") or "").strip()
        predicate = str(triplet.get("predicate") or "").strip()
        obj = str(triplet.get("object") or "").strip()
        confidence = triplet.get("confidence")
        if confidence is None: confidence = 0.8
        
        if not subject or not predicate or not obj:
            logger.debug(f"DROP: Missing required field - {triplet}")
            continue

        # KESİNLİKLE KOMUT/META FİLTRESİ
        obj_clean = obj.lower()
        if predicate == "İSTİYOR" or predicate == "PLANLIYOR":
            COMMAND_KEYWORDS = ["unut", "sil", "temizle", "hafıza", "reset", "sıfırla", "geçmişi", "bilgileri"]
            if any(kw in obj_clean for kw in COMMAND_KEYWORDS):
                logger.info(f"DROP_COMMAND: Filtered out command triplet disguised as fact: '{obj}'")
                continue
        
        # RC-11: Confidence Filter
        if confidence < 0.4: # Çok düşük güven, muhtemelen çok muallak
            logger.info(f"DROP: Low confidence ({confidence}) - {subject} {predicate} {obj}")
            continue

        # 2. FAZ3: Subject pronoun handling
        original_subject = subject
        if is_first_person(subject):
            subject = get_user_anchor(user_id)
            logger.info(f"FIRST_PERSON_MAPPED: '{original_subject}' → '{subject}' (predicate: {predicate})")
        elif is_second_person(subject):
            logger.info(f"SECOND_PERSON_DROPPED: '{subject}' - '{predicate}' - '{obj}'")
            continue
        elif is_other_pronoun(subject):
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
        
        # 6. Durability filter
        durability = catalog.get_durability(predicate_key)
        if durability in {"EPHEMERAL", "SESSION"}:
            logger.info(f"EPHEMERAL_DROPPED: '{canonical}' (durability={durability})")
            continue
        
        
        # 7. Category and Confidence mapping
        graph_category = catalog.get_graph_category(predicate_key)
        
        # FAZ-γ: Identity predicate self-reference mapping [REFINED BATCH-WIDE]
        if graph_category in ["identity", "personal"]:
            obj_lower = obj.lower()
            subj_lower = subject.lower()
            
            # FAZ-γ: Placeholder values check (e.g., "Bilgi Yok", "Bilinmiyor") - Skip extraction if placeholder
            PLACEHOLDERS = ["bilinmiyor", "bilgi yok", "verilmemis", "verilmemiş", "tanimsiz", "tanımlı değil", "belirsiz", "none", "null", "bilgim yok"]
            if any(placeholder in obj_lower for placeholder in PLACEHOLDERS):
                logger.info(f"PLACEHOLDER_DROPPED: Filtered out placeholder object '{obj}' for predicate '{canonical}'")
                continue
            
            # 1. Discover names in this batch (Multi-pass approach)
            batch_user_names = set()
            for t in triplets:
                t_subj = str(t.get("subject") or "").strip()
                t_pred = str(t.get("predicate") or "").strip()
                t_obj = str(t.get("object") or "").strip()
                # Case 1: "Benim adım X"
                if is_first_person(t_subj) and catalog.resolve_predicate(t_pred) == "İSİM":
                    if t_obj and t_obj.lower() not in ["bilinmiyor", "bilgi yok", "verilmemiş"]:
                        batch_user_names.add(t_obj.lower())
                # Case 2: "Muhammet İSİM Muhammet"
                if t_subj.lower() == t_obj.lower() and catalog.resolve_predicate(t_pred) == "İSİM":
                     if t_obj and t_obj.lower() not in ["bilinmiyor", "bilgi yok", "verilmemiş"]:
                        batch_user_names.add(t_obj.lower())

            # Heuristic A: Explicit self-ref (this triplet)
            is_self_ref = subj_lower in obj_lower or obj_lower in subj_lower
            
            # Heuristic B: Known name reference (DB)
            is_known_name = False
            if known_names:
                for kn in known_names:
                    if subj_lower == kn.lower() or subj_lower == kn.lower().split()[0]:
                        is_known_name = True
                        break
            
            # Heuristic C: Batch name discovery (this batch)
            is_batch_name = any(subj_lower == bn or subj_lower == bn.split()[0] for bn in batch_user_names)

            if is_self_ref or is_known_name or is_batch_name:
                if not subject.startswith("__USER__"):
                    self_ref_original_subject = subject
                    subject = get_user_anchor(user_id)
                    logger.info(f"IDENTITY_ANCHOR_MAPPED: '{self_ref_original_subject}' → '{subject}' (Type: {'SELF-REF' if is_self_ref else 'KNOWN' if is_known_name else 'BATCH'})")
            else:
                logger.info(f"[FAZ-γ DEBUG] No identity match for '{subj_lower}' (category: {graph_category})")
        
        # RC-11: Uncertainty mapping
        drop_thresh = settings.get("DROP_THRESHOLD", 0.4)
        soft_thresh = settings.get("SOFT_SIGNAL_THRESHOLD", 0.7)

        if confidence < drop_thresh:
            logger.info(f"RC-11: Discarding low confidence triplet ({confidence}) for '{predicate_key}'")
            continue

        if confidence < soft_thresh and graph_category == "personal":
             graph_category = "soft_signal"
             logger.info(f"RC-11: Uncertainty detected ({confidence}), forcing to soft_signal")

        # Build cleaned triplet
        cleaned.append({
            "subject": subject,
            "predicate": canonical,
            "object": obj,
            "category": graph_category,
            "confidence": confidence
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
    # Professional Null Check
    if text is None:
        logger.warning(f"extract_and_save: 'text' is None for user {user_id}")
        return []
    
    if not isinstance(text, str):
        logger.warning(f"extract_and_save: 'text' is {type(text)}, expected str. user={user_id}")
        # Try to convert to str if possible, otherwise return
        try:
            text = str(text)
        except:
            return []

    if not text.strip() or len(text.strip()) < 5:
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
                # FAZ-γ: Fetch known identities for anchor mapping
                known_names = await neo4j_manager.get_user_names(user_id)
                
                # FAZ1-2: Apply predicate catalog enforcement before Neo4j write
                cleaned_triplets = sanitize_triplets(triplets, user_id, text, known_names=known_names)
                
                if cleaned_triplets:
                    # FAZ4: MWG karar motoru
                    from atlas.memory.memory_policy import load_policy_for_user
                    from atlas.memory.mwg import decide, Decision
                    from atlas.memory.prospective_store import create_task
                    
                    policy = await load_policy_for_user(user_id)
                    long_term_triplets = []
                    
                    for triplet in cleaned_triplets:
                        result = await decide(triplet, policy, user_id, text)
                        if result.decision == Decision.LONG_TERM:
                            long_term_triplets.append(triplet)
                            logger.info(f"MWG: LONG_TERM - {result.reason}")
                        elif result.decision == Decision.PROSPECTIVE:
                            await create_task(user_id, text, source_turn_id)
                            logger.info(f"MWG: PROSPECTIVE task oluşturuldu")
                        else:
                            logger.info(f"MWG: {result.decision.value} - {result.reason}")
                    
                    if long_term_triplets:
                        logger.info(f"Neo4j: {len(long_term_triplets)} LONG_TERM triplet yazılıyor")
                        await neo4j_manager.store_triplets(long_term_triplets, user_id, source_turn_id)
                        return long_term_triplets
                    else:
                        logger.info("MWG: Tüm triplet'ler drop/PROSPECTIVE")
                        return []
                else:
                    logger.info("Tüm triplet'ler Faz 1 filtreleri tarafından drop edildi.")
                    return []
            else:
                logger.info("Mesajdan anlamlı bir bilgi çıkarılmadı.")
                return []

    except Exception as e:
        import traceback
        logger.error(f"extract_and_save metodunda kritik hata: {str(e)}\n{traceback.format_exc()}")
        return []
