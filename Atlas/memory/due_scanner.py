"""
Atlas Due Task Scanner
----------------------
FAZ 7: Zamanı gelen görevleri (tasks) tarayan ve bildirim (notification) üreten yardımcı bileşen.
"""

import logging
from datetime import datetime
from Atlas.memory.neo4j_manager import neo4j_manager

logger = logging.getLogger(__name__)

async def scan_due_tasks(user_id: str):
    """
    Kullanıcının zamanı gelen görevlerini tarar ve bildirim oluşturur.
    FAZ7-R: String kıyaslaması yerine datetime() kullanımı ve cooldown (60 dk) eklendi.
    """
    now_iso = datetime.now().isoformat()
    
    # Zamanı gelmiş (due_at_dt <= now), hala OPEN olan ve 60 dk içinde uyarılmamış görevleri bul
    query = """
    MATCH (u:User {id: $uid})-[:HAS_TASK]->(t:Task {status: 'OPEN'})
    WHERE t.due_at_dt IS NOT NULL 
      AND datetime(t.due_at_dt) <= datetime($now)
      AND (t.last_notified_at IS NULL OR duration.between(datetime(t.last_notified_at), datetime()).minutes >= 60)
    RETURN t.id as id, t.raw_text as text, t.due_at_raw as due_raw
    """
    
    try:
        due_tasks = await neo4j_manager.query_graph(query, {"uid": user_id, "now": now_iso})
        
        for task in due_tasks:
            # Bildirim oluştur
            notif_data = {
                "message": f"Hatırlatma: {task['text']} (Zamanı: {task['due_raw']})",
                "type": "task_reminder",
                "source": "due_scanner",
                "related_task_id": task['id'],
                "reason": f"Task deadline reached: {task['due_raw']}"
            }
            
            notif_id = await neo4j_manager.create_notification(user_id, notif_data)
            if notif_id:
                # FAZ7-R: Task OPEN kalmaya devam eder, sadece last_notified_at güncellenir
                await neo4j_manager.query_graph(
                    "MATCH (t:Task {id: $tid}) SET t.last_notified_at = datetime()",
                    {"tid": task['id']}
                )
                logger.info(f"DueScanner: {user_id} için görev uyarısı oluşturuldu (veya güncellendi): {task['id']}")
                
    except Exception as e:
        logger.error(f"DueScanner hatası: {e}")

async def list_all_due_soon(limit: int = 10) -> list:
    """
    Sistem genelinde zamanı yaklaşan görevleri listele (Monitor için).
    """
    query = """
    MATCH (u:User)-[:HAS_TASK]->(t:Task {status: 'OPEN'})
    WHERE t.due_at_dt IS NOT NULL
    RETURN u.id as user_id, t.id as task_id, t.raw_text as text, t.due_at_dt as due_at
    ORDER BY t.due_at_dt ASC
    LIMIT $limit
    """
    return await neo4j_manager.query_graph(query, {"limit": limit})
