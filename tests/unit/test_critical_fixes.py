"""
FAZ-α Critical Fixes - Test Suite
==================================
Tests for topic reset fix and memory cleanup mechanism.
"""

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timedelta
from atlas.memory.state import SessionState, StateManager


class TestTopicResetFix:
    """Test critical fix: _hydrated flag reset on topic change"""
    
    def test_hydrated_flag_resets_on_topic_change(self):
        """Test: When topic changes, _hydrated flag should reset to False"""
        # Arrange
        state = SessionState(session_id="test_123")
        state.current_topic = "Kuantum"
        state._hydrated = True  # Simulate hydrated state
        
        # Act
        state.update_topic("Python")
        
        # Assert
        assert state.current_topic == "Python"
        assert state._hydrated == False, "Flag should reset when topic changes"
    
    def test_hydrated_flag_unchanged_for_same_topic(self):
        """Test: SAME topic should not reset flag"""
        # Arrange
        state = SessionState(session_id="test_456")
        state.current_topic = "Kuantum"
        state._hydrated = True
        
        # Act
        state.update_topic("SAME")
        
        # Assert
        assert state.current_topic == "Kuantum"
        assert state._hydrated == True, "Flag should NOT reset for SAME"
    
    def test_hydrated_flag_unchanged_for_chitchat(self):
        """Test: CHITCHAT topic should not reset flag"""
        # Arrange
        state = SessionState(session_id="test_789")
        state.current_topic = "Python"
        state._hydrated = True
        
        # Act
        state.update_topic("CHITCHAT")
        
        # Assert
        assert state.current_topic == "Python"
        assert state._hydrated == True, "Flag should NOT reset for CHITCHAT"


class TestMemoryCleanup:
    """Test memory leak fix: TTL-based session cleanup"""
    
    def test_cleanup_removes_stale_sessions(self):
        """Test: Sessions older than 24h should be removed"""
        # Arrange
        StateManager._states = {}
        StateManager._last_cleanup = datetime.now()
        
        # Create sessions with different ages
        fresh_state = SessionState(session_id="fresh_123")
        fresh_state.last_updated = datetime.now()
        
        stale_state = SessionState(session_id="stale_456")
        stale_state.last_updated = datetime.now() - timedelta(hours=25)  # 25h old
        
        StateManager._states = {
            "fresh_123": fresh_state,
            "stale_456": stale_state
        }
        
        # Act
        StateManager._cleanup_stale_sessions()
        
        # Assert
        assert "fresh_123" in StateManager._states, "Fresh session should remain"
        assert "stale_456" not in StateManager._states, "Stale session should be removed"
    
    def test_cleanup_handles_empty_dict(self):
        """Test: Cleanup should handle empty state dict gracefully"""
        # Arrange
        StateManager._states = {}
        
        # Act & Assert (should not raise exception)
        try:
            StateManager._cleanup_stale_sessions()
            cleanup_success = True
        except Exception:
            cleanup_success = False
        
        assert cleanup_success, "Cleanup should handle empty dict"
    
    def test_periodic_cleanup_triggers(self):
        """Test: Cleanup should trigger after 1 hour"""
        # Arrange
        StateManager._states = {}
        StateManager._last_cleanup = datetime.now() - timedelta(hours=2)  # 2h ago
        
        # Create a stale session
        stale_state = SessionState(session_id="old_session")
        stale_state.last_updated = datetime.now() - timedelta(hours=25)
        StateManager._states["old_session"] = stale_state
        
        # Act
        state = StateManager.get_state("new_session")
        
        # Assert
        # Cleanup should have been triggered, removing stale session
        assert "old_session" not in StateManager._states, "Periodic cleanup should remove stale sessions"
        assert "new_session" in StateManager._states, "New session should be created"


class TestIntegratedBehavior:
    """Test integrated behavior of both fixes"""
    
    def test_topic_change_after_hydration_allows_rehydration(self):
        """Test: Server restart scenario with topic change"""
        # Scenario:
        # 1. Hydrate with "Kuantum"
        # 2. User changes topic to "Python"
        # 3. Server restarts (simulation)
        # 4. Hydration should work again because flag was reset
        
        # Step 1: Initial hydration
        state = SessionState(session_id="test_restart")
        state.current_topic = "Kuantum"
        state._hydrated = True
        
        # Step 2: Topic change
        state.update_topic("Python")
        assert state._hydrated == False, "Flag should be reset"
        
        # Step 3: Simulate server restart (topic reset to default)
        state.current_topic = "Genel"
        
        # Step 4: Hydration check
        # In real scenario, orchestrator would check:
        # if state.current_topic == "Genel" and not state._hydrated:
        can_hydrate = (state.current_topic == "Genel" and not state._hydrated)
        assert can_hydrate, "Should allow hydration after topic change and restart"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
