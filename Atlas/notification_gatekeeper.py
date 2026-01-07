"""
ATLAS Notification Gatekeeper
-----------------------------
RC-2 Hardening: Bildirimlerin gönderilip gönderilmeyeceğine karar veren merkezi denetleyici.
Quiet hours (sessiz saatler), günlük yorgunluk (fatigue) ve opt-in ayarlarını tek yerden yönetir.
"""

import logging
from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

async def should_emit_notification(user_id: str, neo4j_manager, now: Optional[datetime] = None) -> tuple[bool, str]:
    """
    Bildirim gönderimini kurallara göre denetler. (RC-4: Timezone aware)
    
    Returns:
        (bool, reason_code): (True, "ok") veya (False, "reason_why_blocked")
    """
    # 0. TIMEZONE AYARI
    tz_str = await neo4j_manager.get_user_timezone(user_id)
    try:
        user_tz = ZoneInfo(tz_str)
    except Exception:
        user_tz = ZoneInfo("Europe/Istanbul")

    if now is None:
        # Sistem zamanını UTC olarak al ve kullanıcı zaman dilimine çevir
        now = datetime.now(dt_timezone.utc).astimezone(user_tz)
    elif now.tzinfo is None:
        # Naive datetime ise kullanıcı zaman diliminde varsay
        now = now.replace(tzinfo=user_tz)
    else:
        # Zaten aware ise kullanıcı zaman dilimine convert et
        now = now.astimezone(user_tz)
        
    # 1. AYARLARI ÇEK
    settings = await neo4j_manager.get_user_settings(user_id)
    
    # 2. OPT-IN KONTROLÜ
    if not settings.get("notifications_enabled"):
        return False, "disabled"
        
    # 3. QUIET HOURS KONTROLÜ
    q_start = settings.get("quiet_hours_start")
    q_end = settings.get("quiet_hours_end")
    
    if q_start and q_end:
        now_str = now.strftime("%H:%M")
        if _is_within_time_range(now_str, q_start, q_end):
            return False, "quiet_hours"
            
    # 4. FATIGUE (GÜNLÜK LİMİT) KONTROLÜ
    daily_limit = settings.get("max_notifications_per_day", 5)
    daily_count = await neo4j_manager.count_daily_notifications(user_id)
    
    if daily_count >= daily_limit:
        return False, f"fatigue:{daily_count}"
        
    return True, f"ok:daily={daily_count}"

def _is_within_time_range(current: str, start: str, end: str) -> bool:
    """Zaman aralığı kontrolü (HH:MM)."""
    try:
        if start < end:
            return start <= current <= end
        else: # Geceyi aşan aralık (örn: 22:00 - 08:00)
            return current >= start or current <= end
    except Exception:
        return False
