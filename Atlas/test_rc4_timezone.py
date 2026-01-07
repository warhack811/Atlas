import unittest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime
from zoneinfo import ZoneInfo
from Atlas.notification_gatekeeper import should_emit_notification

class TestRC4Timezone(unittest.IsolatedAsyncioTestCase):
    """Timezone standardizasyonu ve user-specific TZ testleri."""

    @patch('Atlas.memory.neo4j_manager.neo4j_manager.get_user_timezone', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.get_user_settings', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.count_daily_notifications', new_callable=AsyncMock)
    async def test_quiet_hours_respects_user_timezone(self, mock_count, mock_settings, mock_tz):
        # Setup: Kullanıcı Tokyo'da (UTC+9), şu an UTC 20:00 (Tokyo'da sabah 05:00)
        # Quiet hours: 22:00 - 08:00
        mock_tz.return_value = "Asia/Tokyo"
        mock_settings.return_value = {
            "notifications_enabled": True,
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "08:00"
        }
        mock_count.return_value = 0
        
        # 20:00 UTC -> 05:00 Tokyo
        from datetime import timezone
        now_utc = datetime(2026, 1, 1, 20, 0, tzinfo=timezone.utc)
        
        from Atlas.memory.neo4j_manager import neo4j_manager
        is_allowed, reason = await should_emit_notification("u1", neo4j_manager, now=now_utc)
        
        # Tokyo'da 05:00 sessiz saatler içinde (22:00-08:00), engellenmeli
        self.assertFalse(is_allowed)
        self.assertEqual(reason, "quiet_hours")

    @patch('Atlas.memory.neo4j_manager.neo4j_manager.get_user_timezone', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.get_user_settings', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.count_daily_notifications', new_callable=AsyncMock)
    async def test_midnight_wrap_quiet_hours(self, mock_count, mock_settings, mock_tz):
        # Setup: Europe/Istanbul (UTC+3), 23:30 (Sessiz saatler içinde: 22:00-08:00)
        mock_tz.return_value = "Europe/Istanbul"
        mock_settings.return_value = {
            "notifications_enabled": True,
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "08:00"
        }
        mock_count.return_value = 0
        from datetime import timezone
        now_utc = datetime(2026, 1, 1, 20, 30, tzinfo=timezone.utc) # 23:30 Istanbul
        
        from Atlas.memory.neo4j_manager import neo4j_manager
        is_allowed, reason = await should_emit_notification("u1", neo4j_manager, now=now_utc)
        self.assertFalse(is_allowed)
        self.assertEqual(reason, "quiet_hours")

if __name__ == "__main__":
    unittest.main()
