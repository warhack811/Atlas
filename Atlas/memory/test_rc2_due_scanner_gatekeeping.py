import unittest
from unittest.mock import patch, AsyncMock, MagicMock
from Atlas.memory.due_scanner import scan_due_tasks

class TestRC2DueScannerGatekeeping(unittest.IsolatedAsyncioTestCase):
    
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.query_graph', new_callable=AsyncMock)
    @patch('Atlas.notification_gatekeeper.should_emit_notification', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.create_notification', new_callable=AsyncMock)
    async def test_due_scanner_blocked_by_gatekeeper(self, mock_create, mock_gate, mock_query):
        """Gatekeeper bildirim gönderimine izin vermezse due_scanner bildirim oluşturmamalı."""
        # 1. Görev bul
        mock_query.return_value = [{"id": "t1", "text": "Task 1", "due_raw": "today"}]
        
        # 2. Gatekeeper engelle (ör: quiet_hours)
        mock_gate.return_value = (False, "quiet_hours")
        
        await scan_due_tasks("u1")
        
        # 3. create_notification çağrılmamalı
        mock_create.assert_not_called()

    @patch('Atlas.memory.neo4j_manager.neo4j_manager.query_graph', new_callable=AsyncMock)
    @patch('Atlas.notification_gatekeeper.should_emit_notification', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.create_notification', new_callable=AsyncMock)
    async def test_due_scanner_allowed_by_gatekeeper(self, mock_create, mock_gate, mock_query):
        """Gatekeeper izin verirse due_scanner bildirim oluşturmalı."""
        mock_query.return_value = [{"id": "t1", "text": "Task 1", "due_raw": "today", "due_dt_obj": None}]
        mock_gate.return_value = (True, "ok")
        mock_create.return_value = "notif_123"
        
        await scan_due_tasks("u1")
        
        # 3. create_notification çağrılmalı
        mock_create.assert_called_once()

if __name__ == "__main__":
    unittest.main()
