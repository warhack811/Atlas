import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from Atlas.key_manager import KeyManager, KeyStatus, KeyStats
import Atlas.key_manager as key_manager_module

# Fixture to reset KeyManager state before and after each test
@pytest.fixture(autouse=True)
def reset_key_manager():
    # Store original state
    original_pools = KeyManager._pools.copy()
    original_initialized = KeyManager._initialized

    # Reset state
    KeyManager._pools = {"groq": {}, "gemini": {}}
    KeyManager._initialized = False

    yield

    # Restore original state (though tests shouldn't depend on it)
    KeyManager._pools = original_pools
    KeyManager._initialized = original_initialized

# Helper for datetime mocking
class MockDatetime(datetime):
    _now = datetime(2023, 1, 1, 12, 0, 0)

    @classmethod
    def now(cls):
        return cls._now

    @classmethod
    def set_now(cls, dt):
        cls._now = dt

def test_initialization():
    groq_keys = ["groq_key_1", "groq_key_2"]
    gemini_keys = ["gemini_key_1"]

    KeyManager.initialize(groq_keys=groq_keys, gemini_keys=gemini_keys)

    assert KeyManager._initialized is True
    assert len(KeyManager._pools["groq"]) == 2
    assert len(KeyManager._pools["gemini"]) == 1

    # Check if keys are correctly assigned
    key_stats = list(KeyManager._pools["groq"].values())[0]
    assert isinstance(key_stats, KeyStats)
    assert hasattr(key_stats, "_actual_key")
    assert key_stats._actual_key in groq_keys
    assert key_stats.key_masked.startswith("...") or key_stats.key_masked == "****"

def test_detect_provider():
    assert KeyManager._detect_provider("gemini-pro") == "gemini"
    assert KeyManager._detect_provider("google-gemini") == "gemini"
    assert KeyManager._detect_provider("llama3-70b") == "groq"
    assert KeyManager._detect_provider("mixtral") == "groq"
    assert KeyManager._detect_provider(None) == "groq"
    assert KeyManager._detect_provider("") == "groq"

def test_get_best_key_selection_logic():
    # Setup manually to control stats
    KeyManager._pools["groq"] = {}
    KeyManager._initialized = True

    # Key 1: High usage, low success
    k1 = KeyStats(key_id="k1", key_masked="...k1")
    k1._actual_key = "key1"
    k1.daily_requests = 100
    k1.successful_requests = 50
    k1.total_requests = 100 # 50% success
    KeyManager._pools["groq"]["k1"] = k1

    # Key 2: Low usage, high success (Should be picked)
    k2 = KeyStats(key_id="k2", key_masked="...k2")
    k2._actual_key = "key2"
    k2.daily_requests = 10
    k2.successful_requests = 10
    k2.total_requests = 10 # 100% success
    KeyManager._pools["groq"]["k2"] = k2

    # Key 3: Moderate usage, moderate success
    k3 = KeyStats(key_id="k3", key_masked="...k3")
    k3._actual_key = "key3"
    k3.daily_requests = 50
    k3.successful_requests = 40
    k3.total_requests = 50 # 80% success
    KeyManager._pools["groq"]["k3"] = k3

    best_key = KeyManager.get_best_key("llama3")
    assert best_key == "key2"

def test_get_best_key_unavailable():
    KeyManager._pools["groq"] = {}
    KeyManager._initialized = True

    k1 = KeyStats(key_id="k1", key_masked="...k1", status=KeyStatus.DISABLED)
    k1._actual_key = "key1"
    KeyManager._pools["groq"]["k1"] = k1

    best_key = KeyManager.get_best_key("llama3")
    assert best_key is None

def test_report_success():
    KeyManager.initialize(groq_keys=["key1"])

    KeyManager.report_success("key1", model_id="llama3")

    stats = KeyManager._find_by_key("key1")
    assert stats.total_requests == 1
    assert stats.successful_requests == 1
    assert stats.daily_requests == 1
    assert stats.model_usage["llama3"] == 1
    assert stats.last_used is not None

def test_report_error_429_rate_limit():
    KeyManager.initialize(groq_keys=["key1"])

    # Mock datetime to check cooldown
    with patch("Atlas.key_manager.datetime", MockDatetime):
        MockDatetime.set_now(datetime(2023, 1, 1, 12, 0, 0))

        KeyManager.report_error("key1", status_code=429, error_msg="Rate limit exceeded")

        stats = KeyManager._find_by_key("key1")
        assert stats.status == KeyStatus.COOLDOWN
        assert stats.rate_limit_hits == 1
        # Check cooldown time (default 60s)
        expected_cooldown = MockDatetime.now() + timedelta(seconds=60)
        assert stats.cooldown_until == expected_cooldown

def test_report_error_quota_exhausted():
    KeyManager.initialize(groq_keys=["key1"])
    model_id = "llama3"

    with patch("Atlas.key_manager.datetime", MockDatetime):
        MockDatetime.set_now(datetime(2023, 1, 1, 12, 0, 0))

        # quota error
        KeyManager.report_error("key1", status_code=403, error_msg="Quota exhausted", model_id=model_id)

        stats = KeyManager._find_by_key("key1")

        assert model_id in stats.model_exhausted
        reset_time = stats.model_exhausted[model_id]

        now = MockDatetime.now()
        expected_reset = datetime(now.year, now.month, now.day) + timedelta(days=1)
        assert reset_time == expected_reset

def test_report_error_503_capacity():
    KeyManager.initialize(groq_keys=["key1"])

    KeyManager.report_error("key1", status_code=503, error_msg="Service over capacity")

    stats = KeyManager._find_by_key("key1")
    assert stats.failed_requests == 1
    # Should stay healthy (or at least not disabled/cooldown for 503 per logic)
    assert stats.status == KeyStatus.HEALTHY

def test_check_daily_reset():
    KeyManager.initialize(groq_keys=["key1"])
    stats = KeyManager._find_by_key("key1")
    stats.daily_requests = 100
    stats.daily_reset_date = "2023-01-01"

    # Mock datetime to next day
    with patch("Atlas.key_manager.datetime", MockDatetime):
        MockDatetime.set_now(datetime(2023, 1, 2, 12, 0, 0))

        # Trigger reset via get_best_key or explicit call (if accessible)
        # _check_daily_reset is called in get_best_key
        KeyManager._check_daily_reset()

        assert stats.daily_requests == 0
        assert stats.daily_reset_date == "2023-01-02"

def test_is_available_cooldown_expiry():
    stats = KeyStats(key_id="k1", key_masked="...")
    stats.status = KeyStatus.COOLDOWN

    # Cooldown expired
    with patch("Atlas.key_manager.datetime", MockDatetime):
        now = datetime(2023, 1, 1, 12, 0, 0)
        MockDatetime.set_now(now)
        stats.cooldown_until = now - timedelta(seconds=1) # Expired

        assert stats.is_available() is True
        assert stats.status == KeyStatus.HEALTHY

def test_is_available_model_exhaustion():
    stats = KeyStats(key_id="k1", key_masked="...")
    model_id = "llama3"

    with patch("Atlas.key_manager.datetime", MockDatetime):
        now = datetime(2023, 1, 1, 12, 0, 0)
        MockDatetime.set_now(now)

        # Exhausted until tomorrow
        stats.model_exhausted[model_id] = now + timedelta(days=1)

        assert stats.is_available(model_id) is False

        # Check another model
        assert stats.is_available("other_model") is True

def test_get_stats():
    KeyManager.initialize(groq_keys=["key1"])
    stats_list = KeyManager.get_stats()

    assert isinstance(stats_list, list)
    assert len(stats_list) == 1
    assert "key_id" in stats_list[0]
    assert "success_rate" in stats_list[0]

def test_auto_initialize_mock():
    # Reset initialized state
    KeyManager._initialized = False
    KeyManager._pools = {"groq": {}, "gemini": {}}

    with patch("Atlas.config.get_groq_api_keys", return_value=["auto_key"]), \
         patch("Atlas.config.get_gemini_api_keys", return_value=[]):

        best = KeyManager.get_best_key("llama3")
        assert best == "auto_key"
        assert KeyManager._initialized is True
