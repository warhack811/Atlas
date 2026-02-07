import sys
from unittest.mock import MagicMock
from datetime import datetime

# --- Mocking Infrastructure ---
# Atlas.api has many top-level dependencies that are not available in the test environment.
# We mock them here to allow the import of the specific utility function we want to test.
mock_modules = [
    "fastapi", "fastapi.staticfiles", "fastapi.responses", "fastapi.middleware.cors",
    "pydantic", "pydantic_settings", "neo4j", "neo4j.time", "apscheduler",
    "apscheduler.schedulers.asyncio", "httpx", "google", "google.genai",
    "google.api_core", "qdrant_client", "redis", "redis.asyncio", "itsdangerous",
    "Atlas.memory.semantic_cache", "Atlas.memory.text_normalize", "Atlas.config",
    "Atlas.rdr", "Atlas.auth", "Atlas.safety", "Atlas.memory",
    "Atlas.orchestrator", "Atlas.dag_executor", "Atlas.synthesizer",
    "Atlas.memory.neo4j_manager", "Atlas.memory.request_context",
    "Atlas.memory.trace", "Atlas.memory.state"
]

for m in mock_modules:
    if m not in sys.modules:
        sys.modules[m] = MagicMock()

# Define a dummy DateTime class for neo4j.time.DateTime to support isinstance checks
class DummyNeo4jDateTime:
    def __init__(self, iso_val):
        self.iso_val = iso_val
    def isoformat(self):
        return self.iso_val

sys.modules["neo4j.time"].DateTime = DummyNeo4jDateTime

import pytest
# Now we can safely import the utility function
from Atlas.api import serialize_neo4j_value

# --- Tests ---

def test_serialize_basic_types():
    """Test serialization of basic Python types (int, str, float, bool, None)."""
    assert serialize_neo4j_value(1) == 1
    assert serialize_neo4j_value("test") == "test"
    assert serialize_neo4j_value(1.5) == 1.5
    assert serialize_neo4j_value(True) == True
    assert serialize_neo4j_value(None) is None

def test_serialize_datetime():
    """Test serialization of standard datetime objects to ISO format."""
    dt = datetime(2023, 10, 27, 12, 30, 0)
    assert serialize_neo4j_value(dt) == dt.isoformat()

def test_serialize_neo4j_datetime():
    """Test serialization of Neo4j-specific DateTime objects."""
    iso_str = "2023-10-27T12:30:00Z"
    mock_dt = DummyNeo4jDateTime(iso_str)
    assert serialize_neo4j_value(mock_dt) == iso_str

def test_serialize_list():
    """Test recursive serialization of lists containing various types."""
    dt = datetime(2023, 10, 27, 12, 30, 0)
    input_list = [1, "test", dt]
    expected_list = [1, "test", dt.isoformat()]
    assert serialize_neo4j_value(input_list) == expected_list

def test_serialize_dict():
    """Test recursive serialization of dictionaries containing various types."""
    dt = datetime(2023, 10, 27, 12, 30, 0)
    input_dict = {"a": 1, "b": dt}
    expected_dict = {"a": 1, "b": dt.isoformat()}
    assert serialize_neo4j_value(input_dict) == expected_dict

def test_serialize_nested():
    """Test recursive serialization of complex nested structures (mix of dicts and lists)."""
    dt = datetime(2023, 10, 27, 12, 30, 0)
    iso_str = "2023-10-27T12:30:00Z"
    neo4j_dt = DummyNeo4jDateTime(iso_str)

    input_data = {
        "list": [1, {"nested_dt": dt, "neo4j_dt": neo4j_dt}],
        "dt": dt,
        "simple": "val"
    }
    expected_data = {
        "list": [1, {"nested_dt": dt.isoformat(), "neo4j_dt": iso_str}],
        "dt": dt.isoformat(),
        "simple": "val"
    }
    assert serialize_neo4j_value(input_data) == expected_data

def test_serialize_empty():
    """Test serialization of empty lists and dictionaries."""
    assert serialize_neo4j_value([]) == []
    assert serialize_neo4j_value({}) == {}

def test_serialize_recursive_list_in_dict():
    """Test specifically for list inside a dict to ensure recursive depth."""
    dt = datetime(2023, 1, 1)
    data = {"items": [dt, {"date": dt}]}
    expected = {"items": [dt.isoformat(), {"date": dt.isoformat()}]}
    assert serialize_neo4j_value(data) == expected
