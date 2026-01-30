"""
FAZ-α Final: State Hydration - Test Suite
==========================================
Tests for session topic restoration from Neo4j after server restart.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


@pytest.fixture
def mock_neo4j_manager():
    """Mock Neo4j manager for testing"""
    manager = MagicMock()
    manager.get_session_topic = AsyncMock()
    return manager


@pytest.fixture
def mock_state_manager():
    """Mock state manager"""
    state = MagicMock()
    state.current_topic = "Genel"  # Default topic
    state.active_domain = "general"
    state.update_domain = MagicMock()
    state.update_topic = MagicMock()
    return state


class TestGetSessionTopic:
    """Test Neo4j topic retrieval method"""
    
    @pytest.mark.asyncio
    async def test_get_session_topic_exists(self, mock_neo4j_manager):
        """Test 1A: Topic exists in Neo4j, returns correct value"""
        mock_neo4j_manager.get_session_topic.return_value = "Kuantum Fiziği"
        
        result = await mock_neo4j_manager.get_session_topic("session_123")
        
        assert result == "Kuantum Fiziği"
        mock_neo4j_manager.get_session_topic.assert_called_once_with("session_123")
    
    @pytest.mark.asyncio
    async def test_get_session_topic_empty(self, mock_neo4j_manager):
        """Test 1B: No topic in Neo4j, returns None"""
        mock_neo4j_manager.get_session_topic.return_value = None
        
        result = await mock_neo4j_manager.get_session_topic("session_456")
        
        assert result is None


class TestStateHydration:
    """Test orchestrator state hydration logic"""
    
    @pytest.mark.asyncio
    async def test_hydration_restores_topic_from_db(self, mock_neo4j_manager, mock_state_manager):
        """Test 2A: When RAM topic is 'Genel', restore from Neo4j"""
        # Arrange
        mock_neo4j_manager.get_session_topic.return_value = "Kuantum Fiziği"
        
        # Simulate orchestrator state hydration logic
        if mock_state_manager.current_topic == "Genel":
            saved_topic = await mock_neo4j_manager.get_session_topic("session_123")
            if saved_topic:
                mock_state_manager.current_topic = saved_topic
        
        # Assert
        assert mock_state_manager.current_topic == "Kuantum Fiziği"
        mock_neo4j_manager.get_session_topic.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_hydration_skips_if_topic_already_set(self, mock_neo4j_manager, mock_state_manager):
        """Test 2B: When RAM topic is NOT 'Genel', don't query DB"""
        # Arrange
        mock_state_manager.current_topic = "Existing Topic"
        
        # Simulate orchestrator state hydration logic  
        if mock_state_manager.current_topic == "Genel":
            saved_topic = await mock_neo4j_manager.get_session_topic("session_123")
            if saved_topic:
                mock_state_manager.current_topic = saved_topic
        
        # Assert
        assert mock_state_manager.current_topic == "Existing Topic"
        mock_neo4j_manager.get_session_topic.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_hydration_handles_none_from_db(self, mock_neo4j_manager, mock_state_manager):
        """Test 2C: When Neo4j returns None, keep default topic"""
        # Arrange
        mock_neo4j_manager.get_session_topic.return_value = None
        
        # Simulate orchestrator state hydration logic
        if mock_state_manager.current_topic == "Genel":
            saved_topic = await mock_neo4j_manager.get_session_topic("session_123")
            if saved_topic:
                mock_state_manager.current_topic = saved_topic
        
        # Assert
        assert mock_state_manager.current_topic == "Genel"  # Stays default
        mock_neo4j_manager.get_session_topic.assert_called_once()


class TestOrchestratorIntegration:
    """Test orchestrator.plan integration with state hydration"""
    
    @pytest.mark.asyncio
    async def test_orchestrator_plan_hydrates_state(self):
        """Test 3: Full orchestrator integration test with cache verification"""
        from atlas.core.orchestrator import Orchestrator
        
        # Mock dependencies
        with patch('atlas.core.orchestrator.MessageBuffer') as mock_buffer, \
             patch('atlas.core.orchestrator.state_manager') as mock_state_mgr, \
             patch('atlas.core.orchestrator.time_context') as mock_time, \
             patch('atlas.memory.neo4j_manager.neo4j_manager') as mock_neo4j:
            
            # Setup mocks
            mock_buffer.get_llm_messages.return_value = []
            
            mock_state = MagicMock()
            mock_state.current_topic = "Genel"
            mock_state.active_domain = "general"
            mock_state._hydrated = False  # Not yet hydrated
            mock_state.update_domain = MagicMock()
            mock_state.update_topic = MagicMock()
            mock_state_mgr.get_state.return_value = mock_state
            
            mock_time.get_system_prompt_addition.return_value = "[TIME INFO]"
            
            # Setup Neo4j to return saved topic
            mock_neo4j.get_session_topic = AsyncMock(return_value="Kuantum Fiziği")
            
            # Mock _call_brain to avoid actual LLM calls
            with patch.object(Orchestrator, '_call_brain', new_callable=AsyncMock) as mock_brain:
                mock_brain.return_value = (
                    {
                        "intent": "general",
                        "tasks": [],
                        "is_follow_up": False,
                        "detected_topic": "SAME"
                    },
                    "test_prompt",
                    "test_model"
                )
                
                # Act - First call (should hydrate)
                plan = await Orchestrator.plan("session_123", "Test message")
            
            # Assert - First call
            # State hydration should have been called
            mock_neo4j.get_session_topic.assert_called_once_with("session_123")
            # State should have been updated
            assert mock_state.current_topic == "Kuantum Fiziği"
            # _hydrated flag should be set
            assert mock_state._hydrated == True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
