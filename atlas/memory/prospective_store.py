"""
Atlas Prospective Memory Store
-------------------------------
FAZ 4: Gelecek hatırlatma/task kayıt sistemi.

Bu modül, PROSPECTIVE kararı alan triplet'leri Task node olarak Neo4j'ye kaydeder.
UI bağlama için hazır - task listesi ve yönetimi kolayca eklenebilir.
"""

from typing import Optional, List, Dict
import uuid
from datetime import datetime


async def create_task(
    user_id: str,
    raw_text: str,
    source_turn_id: Optional[str] = None,
    due_at: Optional[str] = None
) -> str:
    """
    Prospective task oluştur (Neo4j Task node).
    
    UI Bağlama Noktası:
        Task node'ları UI'dan listelenebilir/yönetilebilir.
        due_at parse edilebilir (FAZ7'de datetime extraction)
    
    Args:
        user_id: Kullanıcı ID
        raw_text: Orijinal mesaj ("Yarın saat 10'da toplantı")
        source_turn_id: Bu task'ı yaratan turn ID (provenance)
        due_at: Hedef tarih/zaman (opsiyonel, MVP: None)
    
    Returns:
        Task ID (UUID)
    
    Örnek:
        >>> task_id = await create_task("user_123", "Yarın su iç hatırlat")
        >>> print(f"Task oluşturuldu: {task_id}")
    """
    from atlas.memory.neo4j_manager import neo4j_manager
    import dateparser
    from zoneinfo import ZoneInfo
    
    task_id = str(uuid.uuid4())[:8]
    
    # RC-4: User timezone fetch
    tz_str = await neo4j_manager.get_user_timezone(user_id)
    try:
        user_tz = ZoneInfo(tz_str)
    except Exception:
        user_tz = ZoneInfo("Europe/Istanbul")
    
    # FAZ7: due_at parsing (Türkçe destekli)
    due_at_dt = None
    if due_at:
        try:
            # dateparser ile doğal dil işleme (yarın, 3 gün sonra vb.)
            # RC-4: Kullanıcı zaman dilimine göre base al
            from datetime import timezone as dt_timezone
            now_local = datetime.now(dt_timezone.utc).astimezone(user_tz)
            
            parsed_dt = dateparser.parse(
                due_at, 
                languages=['tr'],
                settings={'PREFER_DATES_FROM': 'future', 'RELATIVE_BASE': now_local}
            )
            if parsed_dt:
                # RC-4: Timezone aware ISO output
                if parsed_dt.tzinfo is None:
                    parsed_dt = parsed_dt.replace(tzinfo=user_tz)
                due_at_dt = parsed_dt.isoformat()
        except Exception as e:
            from atlas.logger import logger
            logger.warning(f"Tarih ayrıştırma hatası ('{due_at}'): {e}")

    query = """
    MERGE (u:User {id: $uid})
    CREATE (t:Task {
        id: $task_id,
        user_id: $uid,
        created_at: datetime(),
        status: 'OPEN',
        raw_text: $raw_text,
        source_turn_id: $source_turn_id,
        due_at_raw: $due_at_raw,
        due_at_dt: datetime($due_at_dt),
        last_notified_at: null,
        notified_count: 0
    })
    MERGE (u)-[:HAS_TASK]->(t)
    RETURN t.id as task_id
    """
    
    try:
        result = await neo4j_manager.query_graph(query, {
            "uid": user_id,
            "task_id": task_id,
            "raw_text": raw_text,
            "source_turn_id": source_turn_id,
            "due_at_raw": due_at,
            "due_at_dt": due_at_dt
        })
        return task_id
    except Exception as e:
        from atlas.logger import logger
        logger.error(f"Task oluşturma hatası: {e}")
        return None


async def list_open_tasks(user_id: str, limit: int = 10) -> List[Dict]:
    """
    Kullanıcının açık task'lerini listele.
    
    UI Bağlama Noktası:
        Task listesi UI'da gösterilebilir ve yönetilebilir.
    
    Args:
        user_id: Kullanıcı ID
        limit: Maksimum task sayısı
    
    Returns:
        Task listesi (id, text, created, due_at)
    
    Örnek:
        >>> tasks = await list_open_tasks("user_123")
        >>> for task in tasks:
        >>>     print(f"{task['text']} - {task['created']}")
    """
    from atlas.memory.neo4j_manager import neo4j_manager
    
    query = """
    MATCH (u:User {id: $uid})-[:HAS_TASK]->(t:Task {status: 'OPEN'})
    RETURN t.id as id, t.raw_text as text, t.created_at as created, 
           t.due_at_raw as due_raw, t.due_at_dt as due_dt
    ORDER BY t.created_at DESC
    LIMIT $limit
    """
    
    try:
        result = await neo4j_manager.query_graph(query, {"uid": user_id, "limit": limit})
        return result if result else []
    except Exception as e:
        from atlas.logger import logger
        logger.warning(f"Task listesi alma hatası: {e}")
        return []


async def mark_task_done(user_id: str, task_id: str) -> bool:
    """
    Task'ı tamamlandı olarak işaretle.
    
    UI Bağlama Noktası:
        Task'ler UI'dan tamamlanabilir.
    
    Args:
        user_id: Kullanıcı ID
        task_id: Task ID
    
    Returns:
        True ise başarılı
    """
    from atlas.memory.neo4j_manager import neo4j_manager
    
    query = """
    MATCH (u:User {id: $uid})-[:HAS_TASK]->(t:Task {id: $task_id})
    SET t.status = 'DONE', t.completed_at = datetime()
    RETURN count(t) as updated
    """
    
    try:
        result = await neo4j_manager.query_graph(query, {"uid": user_id, "task_id": task_id})
        return result[0]["updated"] > 0 if result else False
    except Exception as e:
        from atlas.logger import logger
        logger.error(f"Task tamamlama hatası: {e}")
        return False
