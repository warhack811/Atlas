"""
Atlas Lifecycle & Conflict Engine
----------------------------------
FAZ 5: EXCLUSIVE/ADDITIVE predicate lifecycle yönetimi.

Bu modül, FACT relationship'leri yazarken temporal conflict resolution sağlar:
- EXCLUSIVE: Aynı (subject, predicate) için sadece bir ACTIVE object
- ADDITIVE: Aynı (subject, predicate) için N ACTIVE object

Örnek:
- YAŞAR_YER İstanbul → Ankara: Eski ilişki SUPERSEDED olur
- SEVER Pizza + SEVER Sushi: İkisi de ACTIVE kalır
"""

import logging
from typing import List, Dict, Tuple, Optional
from Atlas.config import Config, MEMORY_CONFIDENCE_SETTINGS
from Atlas.memory.neo4j_manager import neo4j_manager

logger = logging.getLogger(__name__)


async def resolve_conflicts(
    triplets: List[Dict],
    user_id: str,
    source_turn_id: str,
    catalog
) -> Tuple[List[Dict], List[Dict]]:
    """
    EXCLUSIVE/ADDITIVE lifecycle kurallarını uygula.
    
    Args:
        triplets: LONG_TERM triplet'ler (MWG'den geçmiş)
        user_id: Kullanıcı ID
        source_turn_id: Mevcut turn ID
        catalog: PredicateCatalog instance
    
    Returns:
        (new_triplets, supersede_operations)
        - new_triplets: Yaz\u0131lacak yeni triplet'ler
        - supersede_operations: SUPERSEDED i\u015faretlemesi için dict'ler
    
    Logic:
    1. Her triplet i\u00e7in predicate type'\u0131 kontrol et (EXCLUSIVE vs ADDITIVE)
    2. EXCLUSIVE ise: Ayn\u0131 subject+predicate var m\u0131? Object farkl\u0131ysa supersede
    3. ADDITIVE ise: Ayn\u0131 subject+predicate+object var m\u0131? Varsa update, yoksa new
    """
    from Atlas.memory.neo4j_manager import neo4j_manager
    
    new_triplets = []
    supersede_operations = []
    
    # Phase 1: Pre-fetch EXCLUSIVE relationships to avoid N+1 queries
    exclusive_pairs = []
    if catalog:
        for triplet in triplets:
            predicate = triplet.get("predicate", "")
            subject = triplet.get("subject", "")

            # Resolve predicate
            pred_key = catalog.resolve_predicate(predicate)
            if pred_key and catalog.get_type(pred_key) == "EXCLUSIVE":
                 exclusive_pairs.append({
                     "subject": subject,
                     "predicate": predicate
                 })

    # Batch fetch
    existing_exclusive_map = await _batch_find_active_relationships(user_id, exclusive_pairs)

    # Phase 2: Process triplets
    for triplet in triplets:
        predicate = triplet.get("predicate", "")
        subject = triplet.get("subject", "")
        obj = triplet.get("object", "")
        confidence = triplet.get("confidence", 0.8)
        
        if not catalog:
            # Catalog yoksa fail-safe: add as is
            new_triplets.append(triplet)
            continue
        
        # Resolve predicate
        pred_key = catalog.resolve_predicate(predicate)
        if not pred_key:
            logger.warning(f"Lifecycle: Unknown predicate '{predicate}', skipping")
            continue
        
        # Get type
        pred_type = catalog.get_type(pred_key)
        
        if pred_type == "EXCLUSIVE":
            # EXCLUSIVE: Check for existing ACTIVE relationship with same subject+predicate
            # Use pre-fetched map instead of querying DB
            key = (subject, predicate)
            existing = existing_exclusive_map.get(key)
            
            if existing:
                existing_object = existing.get("object")
                existing_confidence = existing.get("confidence", 1.0)
                
                if existing_object == obj:
                    # Same value - no conflict, will be updated by MERGE
                    logger.info(f"Lifecycle EXCLUSIVE: Same value '{subject}' {predicate} '{obj}' - update")
                    new_triplets.append(triplet)
                else:
                    # RC-11: Conflict Detection
                    # Eğer mevcut bilgi çok güçlüyse ve yeni bilgi de güçlüyse ama farklıysa -> CONFLICT
                    settings = MEMORY_CONFIDENCE_SETTINGS
                    conflict_thresh = settings.get("CONFLICT_THRESHOLD", 0.7)

                    if existing_confidence >= conflict_thresh and confidence >= conflict_thresh:
                        logger.warning(f"Lifecycle CONFLICT: '{subject}' {predicate}: '{existing_object}' (conf: {existing_confidence}) VS '{obj}' (conf: {confidence})")
                        supersede_operations.append({
                            "type": "CONFLICT",
                            "user_id": user_id,
                            "subject": subject,
                            "predicate": predicate,
                            "old_object": existing_object,
                            "new_object": obj,
                            "new_turn_id": source_turn_id
                        })
                        # Her iki bilgiyi de CONFLICTED status'ta tutuyoruz
                        triplet["status"] = "CONFLICTED"
                        new_triplets.append(triplet)
                    else:
                        # Existing confidence düşükse yeni bilgi supersede eder
                        logger.info(f"Lifecycle EXCLUSIVE: '{subject}' {predicate} '{existing_object}' → '{obj}' - superseding (low confidence existing)")
                        supersede_operations.append({
                            "type": "SUPERSEDE",
                            "user_id": user_id,
                            "subject": subject,
                            "predicate": predicate,
                            "old_object": existing_object,
                            "new_turn_id": source_turn_id
                        })
                        new_triplets.append(triplet)
            else:
                # No existing - create new
                logger.info(f"Lifecycle EXCLUSIVE: New '{subject}' {predicate} '{obj}'")
                new_triplets.append(triplet)
        
        elif pred_type == "ADDITIVE":
            # ADDITIVE: Check for exact match (subject+predicate+object)
            exact_exists = await neo4j_manager.fact_exists(user_id, subject, predicate, obj)
            
            if exact_exists:
                # Recurrence - will be updated by MERGE
                logger.info(f"Lifecycle ADDITIVE: Recurrence '{subject}' {predicate} '{obj}'")
                new_triplets.append(triplet)
            else:
                # New value - accumulate
                logger.info(f"Lifecycle ADDITIVE: Accumulate '{subject}' {predicate} '{obj}'")
                new_triplets.append(triplet)
        
        else:
            # Unknown type - default to ADDITIVE behavior
            logger.warning(f"Lifecycle: Unknown type '{pred_type}' for predicate '{predicate}', defaulting to ADDITIVE")
            new_triplets.append(triplet)
    
    return new_triplets, supersede_operations


async def _find_active_relationship(user_id: str, subject: str, predicate: str) -> Dict:
    """
    Belirtilen subject+predicate için ACTIVE ilişkiyi bul.
    
    Args:
        user_id: Kullanıcı ID
        subject: Subject entity
        predicate: Predicate (canonical)
    
    Returns:
        {"object": "...", "turn_id": "..."} veya None
    """
    # Global neo4j_manager kullanılıyor (test mocking için)
    
    query = """
    MATCH (s:Entity {name: $subject})-[r:FACT {predicate: $predicate, user_id: $uid}]->(o:Entity)
    WHERE r.status IS NULL OR r.status = 'ACTIVE'
    RETURN o.name as object, r.source_turn_id_last as turn_id, r.confidence as confidence
    LIMIT 1
    """
    
    try:
        result = await neo4j_manager.query_graph(query, {
            "uid": user_id,
            "subject": subject,
            "predicate": predicate
        })
        return result[0] if result else None
    except Exception as e:
        logger.warning(f"_find_active_relationship hatası: {e}")
        return None

async def _batch_find_active_relationships(user_id: str, pairs: List[Dict[str, str]]) -> Dict[Tuple[str, str], Dict]:
    """
    Batch find active relationships for multiple subject-predicate pairs.
    Returns a dict: (subject, predicate) -> relationship_data
    """
    if not pairs:
        return {}

    # Global neo4j_manager kullanılıyor (test mocking için)
    # UNWIND ile toplu sorgu
    query = """
    UNWIND $pairs as pair
    MATCH (s:Entity {name: pair.subject})-[r:FACT {predicate: pair.predicate, user_id: $uid}]->(o:Entity)
    WHERE r.status IS NULL OR r.status = 'ACTIVE'
    RETURN pair.subject as subject, pair.predicate as predicate, o.name as object, r.source_turn_id_last as turn_id, r.confidence as confidence
    """

    try:
        results = await neo4j_manager.query_graph(query, {
            "uid": user_id,
            "pairs": pairs
        })

        lookup = {}
        if results:
            for row in results:
                key = (row["subject"], row["predicate"])
                # If multiple exist, latest one overwrites (arbitrary but acceptable given EXCLUSIVE constraint)
                lookup[key] = {
                    "object": row["object"],
                    "turn_id": row["turn_id"],
                    "confidence": row["confidence"]
                }
        return lookup
    except Exception as e:
        logger.warning(f"_batch_find_active_relationships error: {e}")
        return {}

async def supersede_relationship(
    user_id: str,
    subject: str,
    predicate: str,
    old_object: str,
    new_turn_id: str,
    op_type: str = "SUPERSEDE"
) -> None:
    """
    Eski ilişkiyi SUPERSEDED veya CONFLICTED olarak işaretle.
    """
    # Global neo4j_manager kullanılıyor (test mocking için)
    status = "SUPERSEDED" if op_type == "SUPERSEDE" else "CONFLICTED"
    
    query = """
    MATCH (s:Entity {name: $subject})-[r:FACT {predicate: $predicate, user_id: $uid}]->(o:Entity {name: $old_obj})
    WHERE r.status IS NULL OR r.status = 'ACTIVE'
    SET r.status = $status,
        r.superseded_by_turn_id = $new_turn_id,
        r.valid_until = datetime(),
        r.updated_at = datetime()
    RETURN count(r) as count
    """
    
    try:
        result = await neo4j_manager.query_graph(query, {
            "uid": user_id,
            "subject": subject,
            "predicate": predicate,
            "old_obj": old_object,
            "new_turn_id": new_turn_id,
            "status": status
        })
        count = result[0]["count"] if result else 0
        logger.info(f"Lifecycle: {count} ilişki {status} olarak işaretlendi")
    except Exception as e:
        logger.error(f"Supersede relationship hatası: {e}")


async def supersede_relationships_batch(operations: List[Dict]) -> int:
    """
    Toplu olarak ilişkileri SUPERSEDED veya CONFLICTED olarak işaretle.
    """
    if not operations:
        return 0

    query = """
    UNWIND $ops AS op
    MATCH (s:Entity {name: op.subject})-[r:FACT {predicate: op.predicate, user_id: op.user_id}]->(o:Entity {name: op.old_object})
    WHERE r.status IS NULL OR r.status = 'ACTIVE'
    SET r.status = CASE WHEN op.type = 'CONFLICT' THEN 'CONFLICTED' ELSE 'SUPERSEDED' END,
        r.superseded_by_turn_id = op.new_turn_id,
        r.valid_until = datetime(),
        r.updated_at = datetime()
    RETURN count(r) as count
    """

    try:
        result = await neo4j_manager.query_graph(query, {"ops": operations})
        count = result[0]["count"] if result else 0
        logger.info(f"Lifecycle: Batch supersede executed for {len(operations)} operations. Modified {count} relationships.")
        return count
    except Exception as e:
        logger.error(f"Batch supersede relationship hatası: {e}")
        return 0
