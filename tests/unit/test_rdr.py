
import pytest
import json
import uuid
from datetime import datetime
import Atlas.rdr as rdr_module
from Atlas.rdr import RDR, save_rdr, get_rdr, get_recent_rdrs

@pytest.fixture(autouse=True)
def clean_storage():
    """Clean _rdr_storage before and after each test."""
    rdr_module._rdr_storage.clear()
    yield
    rdr_module._rdr_storage.clear()

def test_rdr_initialization():
    """Test default values and initialization of RDR."""
    rdr = RDR()
    assert rdr.request_id is not None
    assert len(rdr.request_id) == 8
    assert rdr.timestamp is not None
    assert rdr.message == ""
    assert rdr.intent == "unknown"
    assert rdr.tasks_count == 1
    assert isinstance(rdr.safety_issues, list)
    assert isinstance(rdr.metadata, dict)
    assert rdr.is_multi_task is False
    assert rdr.budget_remaining_pct == 100.0

def test_rdr_create():
    """Test RDR.create method."""
    message = "Test message"
    rdr = RDR.create(message=message)
    assert rdr.message == message
    assert rdr.message_length == len(message)
    assert rdr.request_id is not None
    assert len(rdr.request_id) == 8
    assert rdr.timestamp is not None

def test_to_dict():
    """Test to_dict method."""
    rdr = RDR.create("test")
    rdr.intent = "chat"
    rdr_dict = rdr.to_dict()
    assert isinstance(rdr_dict, dict)
    assert rdr_dict["message"] == "test"
    assert rdr_dict["intent"] == "chat"
    assert rdr_dict["request_id"] == rdr.request_id
    assert rdr_dict["message_length"] == 4

def test_to_json():
    """Test to_json method."""
    rdr = RDR.create("test_json")
    rdr.intent = "query"
    json_str = rdr.to_json()
    assert isinstance(json_str, str)

    data = json.loads(json_str)
    assert data["message"] == "test_json"
    assert data["intent"] == "query"
    assert "timestamp" in data

def test_save_and_get_rdr():
    """Test save_rdr and get_rdr functions."""
    rdr = RDR.create("test_save")
    save_rdr(rdr)

    retrieved_rdr = get_rdr(rdr.request_id)
    assert retrieved_rdr is not None
    assert retrieved_rdr.message == "test_save"
    assert retrieved_rdr.request_id == rdr.request_id

    # Test getting non-existent RDR
    assert get_rdr("non_existent_id") is None

def test_get_recent_rdrs():
    """Test get_recent_rdrs function."""
    # Create RDRs with different timestamps
    rdr1 = RDR.create("msg1")
    rdr1.timestamp = "2023-01-01T10:00:00"

    rdr2 = RDR.create("msg2")
    rdr2.timestamp = "2023-01-01T10:00:02"  # Newer

    rdr3 = RDR.create("msg3")
    rdr3.timestamp = "2023-01-01T10:00:01"  # Middle

    save_rdr(rdr1)
    save_rdr(rdr2)
    save_rdr(rdr3)

    # get_recent_rdrs sorts by timestamp descending (newest first)
    recent = get_recent_rdrs(limit=10)
    assert len(recent) == 3
    assert recent[0].message == "msg2"  # Newest
    assert recent[1].message == "msg3"
    assert recent[2].message == "msg1"  # Oldest

    # Test limit
    recent_limit = get_recent_rdrs(limit=2)
    assert len(recent_limit) == 2
    assert recent_limit[0].message == "msg2"
    assert recent_limit[1].message == "msg3"

def test_storage_max_size_eviction():
    """Test that storage respects _RDR_MAX_SIZE (FIFO/Oldest eviction)."""
    # Temporarily modify max size
    original_max = rdr_module._RDR_MAX_SIZE
    rdr_module._RDR_MAX_SIZE = 2

    try:
        # 1. Add first item
        rdr1 = RDR.create("1")
        rdr1.timestamp = "2023-01-01T10:00:00"
        save_rdr(rdr1)
        assert len(rdr_module._rdr_storage) == 1

        # 2. Add second item (max reached)
        rdr2 = RDR.create("2")
        rdr2.timestamp = "2023-01-01T10:00:01"
        save_rdr(rdr2)
        assert len(rdr_module._rdr_storage) == 2

        # 3. Add third item (eviction needed)
        rdr3 = RDR.create("3")
        rdr3.timestamp = "2023-01-01T10:00:02"
        save_rdr(rdr3)

        assert len(rdr_module._rdr_storage) == 2

        # rdr1 is oldest, should be removed
        assert get_rdr(rdr1.request_id) is None
        assert get_rdr(rdr2.request_id) is not None
        assert get_rdr(rdr3.request_id) is not None

    finally:
        # Restore original max size
        rdr_module._RDR_MAX_SIZE = original_max
