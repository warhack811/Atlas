import unittest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime
from Atlas.observer import Observer

class TestObserverGatekeeping(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.observer = Observer()

    @patch('Atlas.notification_gatekeeper.should_emit_notification', new_callable=AsyncMock)
    async def test_gatekeeper_disabled(self, mock_gate):
        # Case: Notifications disabled
        mock_gate.return_value = (False, "disabled")
        
        # Should return early
        with patch.object(self.observer, '_reason_with_llm', new_callable=AsyncMock) as mock_reason:
            await self.observer.check_triggers("user123")
            mock_reason.assert_not_called()

    @patch('Atlas.notification_gatekeeper.should_emit_notification', new_callable=AsyncMock)
    async def test_gatekeeper_quiet_hours(self, mock_gate):
        # Case: Inside quiet hours
        mock_gate.return_value = (False, "quiet_hours")
        
        with patch.object(self.observer, '_reason_with_llm', new_callable=AsyncMock) as mock_reason:
            await self.observer.check_triggers("user123")
            mock_reason.assert_not_called()

    @patch('Atlas.notification_gatekeeper.should_emit_notification', new_callable=AsyncMock)
    async def test_gatekeeper_fatigue(self, mock_gate):
        # Case: Daily limit reached
        mock_gate.return_value = (False, "fatigue:5")
        
        with patch.object(self.observer, '_reason_with_llm', new_callable=AsyncMock) as mock_reason:
            await self.observer.check_triggers("user123")
            mock_reason.assert_not_called()

    @patch('Atlas.notification_gatekeeper.should_emit_notification', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.query_graph', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.create_notification', new_callable=AsyncMock)
    async def test_check_triggers_persistence(self, mock_create, mock_query, mock_gate):
        # Case: All gates passed, notification generated and saved to DB
        mock_gate.return_value = (True, "ok")
        mock_query.return_value = [{"subject": "S", "predicate": "P", "object": "O"}]
        mock_create.return_value = "notif_123"
        
        with patch.object(self.observer, '_reason_with_llm', new_callable=AsyncMock) as mock_reason:
            mock_reason.return_value = "Dangerous storm!"
            await self.observer.check_triggers("user123")
            
            mock_create.assert_called_once()
            args = mock_create.call_args[0]
            self.assertEqual(args[0], "user123")
            self.assertEqual(args[1]["message"], "Dangerous storm!")

if __name__ == "__main__":
    unittest.main()
