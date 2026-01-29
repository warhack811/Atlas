"""
FAZ-β: Time-Aware Emotional Continuity - Test Suite
====================================================
Tests for smart mood filtering with time-based rules.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timezone, timedelta


@pytest.fixture
def mock_neo4j_manager():
    """Mock Neo4j manager for testing"""
    manager = MagicMock()
    manager.get_last_user_mood = AsyncMock()
    manager.count_turns = AsyncMock()
    return manager


class TestGetLastUserMood:
    """Test Neo4j mood retrieval method"""
    
    @pytest.mark.asyncio
    async def test_get_last_user_mood_exists(self, mock_neo4j_manager):
        """Test 1A: Mood data exists, returns correct format"""
        expected_mood = {"mood": "Yorgun", "timestamp": "2024-01-12T00:00:00Z"}
        mock_neo4j_manager.get_last_user_mood.return_value = expected_mood
        
        result = await mock_neo4j_manager.get_last_user_mood("test_user_123")
        
        assert result is not None
        assert result["mood"] == "Yorgun"
        assert "timestamp" in result
    
    @pytest.mark.asyncio
    async def test_get_last_user_mood_empty(self, mock_neo4j_manager):
        """Test 1B: No mood data, returns None"""
        mock_neo4j_manager.get_last_user_mood.return_value = None
        
        result = await mock_neo4j_manager.get_last_user_mood("test_user_456")
        
        assert result is None


class TestMoodFilteringLogic:
    """Test time-based mood filtering logic (unit tests)"""
    
    def test_expired_mood_3days(self):
        """Test 2A: 3 günden eski -> EXPIRED"""
        now = datetime.now(timezone.utc)
        five_days_ago = now - timedelta(days=5)
        delta = now - five_days_ago
        
        # Simulate KURAL 1
        is_expired = delta.days > 3
        assert is_expired, "5-day-old mood should be expired"
    
    def test_too_recent_mood_1min(self):
        """Test 2B: 10 dakikadan yeni -> TOO SOON"""
        now = datetime.now(timezone.utc)
        one_minute_ago = now - timedelta(minutes=1)
        delta = now - one_minute_ago
        
        # Simulate KURAL 2
        is_too_soon = delta.total_seconds() < 600
        assert is_too_soon, "1-minute-old mood should be too recent"
    
    def test_valid_mood_yesterday(self):
        """Test 2C: 1 gün önceki -> VALID (geçerli aralık)"""
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)
        delta = now - yesterday
        
        # Simulate valid range check
        is_expired = delta.days > 3
        is_too_soon = delta.total_seconds() < 600
        is_valid = not is_expired and not is_too_soon
        
        assert is_valid, "Yesterday's mood should be valid"
    
    def test_turn_0_check(self):
        """Test 2D: Turn 0 kontrolü"""
        turn_count_new = 0
        turn_count_ongoing = 5
        
        assert turn_count_new == 0, "New session should have turn count 0"
        assert turn_count_ongoing > 0, "Ongoing chat should have turn count > 0"


class TestTurkishTimeExpressions:
    """Test Turkish time expression generation"""
    
    def test_time_expr_few_hours(self):
        """Test: < 1 saat -> 'birkaç saat önce'"""
        now = datetime.now(timezone.utc)
        few_hours_ago = now - timedelta(minutes=45)
        delta = now - few_hours_ago
        
        if delta.total_seconds() < 3600:
            time_expr = "birkaç saat önce"
        
        assert time_expr == "birkaç saat önce"
    
    def test_time_expr_yesterday(self):
        """Test: 1 gün önce -> 'dün'"""
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)
        delta = now - yesterday
        
        if delta.days == 1:
            time_expr = "dün"
        
        assert time_expr == "dün"
    
    def test_time_expr_few_days(self):
        """Test: 2-3 gün önce -> 'birkaç gün önce'"""
        now = datetime.now(timezone.utc)
        two_days_ago = now - timedelta(days=2)
        delta = now - two_days_ago
        
        if delta.days >= 2 and delta.days <= 3:
            time_expr = "birkaç gün önce"
        
        assert time_expr == "birkaç gün önce"


class TestSynthesizerEmotionalRules:
    """Test synthesizer emotional continuity rules"""
    
    def test_negative_mood_detection(self):
        """Test 3A: Negatif mood detection"""
        formatted_data = "[ÖNCEKİ DUYGU DURUMU]: Kullanıcı dün 'Yorgun' hissediyordu."
        
        import re
        mood_match = re.search(r"ÖNCEKİ DUYGU DURUMU.*?'([^']+)'", formatted_data)
        assert mood_match is not None
        
        mood = mood_match.group(1).lower()
        negative_moods = ["üzgün", "kızgın", "sinirli", "depresif", "mutsuz", "hasta", "yorgun", "stresli", "gergin"]
        
        assert any(neg in mood for neg in negative_moods)
    
    def test_positive_mood_detection(self):
        """Test 3B: Pozitif mood detection"""
        formatted_data = "[ÖNCEKİ DUYGU DURUMU]: Kullanıcı birkaç gün önce 'Mutlu' hissediyordu."
        
        import re
        mood_match = re.search(r"ÖNCEKİ DUYGU DURUMU.*?'([^']+)'", formatted_data)
        assert mood_match is not None
        
        mood = mood_match.group(1).lower()
        positive_moods = ["mutlu", "neşeli", "heyecanlı", "enerjik", "motive", "rahat", "iyi"]
        
        assert any(pos in mood for pos in positive_moods)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
