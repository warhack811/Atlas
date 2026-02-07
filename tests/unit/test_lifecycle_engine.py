
import pytest
import sys
from unittest.mock import AsyncMock, MagicMock, patch

# Mock dependencies before import
mock_neo4j_manager_module = MagicMock()
mock_neo4j_manager_instance = AsyncMock()
mock_neo4j_manager_module.neo4j_manager = mock_neo4j_manager_instance
sys.modules['Atlas.memory.neo4j_manager'] = mock_neo4j_manager_module

mock_config_module = MagicMock()
mock_config_module.Config = MagicMock()
mock_config_module.MEMORY_CONFIDENCE_SETTINGS = {"CONFLICT_THRESHOLD": 0.7}
sys.modules['Atlas.config'] = mock_config_module

# Mock other dependencies that might be imported
sys.modules['dateparser'] = MagicMock()
sys.modules['dateparser.search'] = MagicMock()
sys.modules['neo4j'] = MagicMock()
sys.modules['pydantic'] = MagicMock()
sys.modules['pydantic_settings'] = MagicMock()

from Atlas.memory.lifecycle_engine import resolve_conflicts

@pytest.fixture
def mock_catalog():
    catalog = MagicMock()
    catalog.resolve_predicate = lambda p: p # Identity for simplicity

    def get_type(key):
        if key == "EXCLUSIVE_PRED":
            return "EXCLUSIVE"
        elif key == "ADDITIVE_PRED":
            return "ADDITIVE"
        return "ADDITIVE"

    catalog.get_type = MagicMock(side_effect=get_type)
    return catalog

@pytest.fixture
def mock_neo4j():
    return mock_neo4j_manager_instance

@pytest.mark.asyncio
async def test_resolve_conflicts_exclusive_no_existing(mock_catalog, mock_neo4j):
    # Setup
    triplets = [{
        "subject": "User",
        "predicate": "EXCLUSIVE_PRED",
        "object": "NewVal",
        "confidence": 0.9
    }]

    # Mock no existing relationship (batch query returns empty)
    mock_neo4j.query_graph.return_value = []

    # Execute
    new_triplets, ops = await resolve_conflicts(triplets, "user1", "turn1", mock_catalog)

    # Verify
    assert len(new_triplets) == 1
    assert len(ops) == 0
    assert new_triplets[0]["object"] == "NewVal"

@pytest.mark.asyncio
async def test_resolve_conflicts_exclusive_existing_same(mock_catalog, mock_neo4j):
    # Setup
    triplets = [{
        "subject": "User",
        "predicate": "EXCLUSIVE_PRED",
        "object": "ExistingVal",
        "confidence": 0.9
    }]

    # Mock existing relationship with same value
    # The batch query returns a list of rows including subject and predicate
    mock_neo4j.query_graph.return_value = [{
        "subject": "User",
        "predicate": "EXCLUSIVE_PRED",
        "object": "ExistingVal",
        "turn_id": "turn0",
        "confidence": 1.0
    }]

    # Execute
    new_triplets, ops = await resolve_conflicts(triplets, "user1", "turn1", mock_catalog)

    # Verify
    assert len(new_triplets) == 1
    assert len(ops) == 0
    assert new_triplets[0]["object"] == "ExistingVal"

@pytest.mark.asyncio
async def test_resolve_conflicts_exclusive_existing_different_supersede(mock_catalog, mock_neo4j):
    # Setup
    triplets = [{
        "subject": "User",
        "predicate": "EXCLUSIVE_PRED",
        "object": "NewVal",
        "confidence": 0.9
    }]

    # Mock existing relationship with different value, low confidence
    mock_neo4j.query_graph.return_value = [{
        "subject": "User",
        "predicate": "EXCLUSIVE_PRED",
        "object": "OldVal",
        "turn_id": "turn0",
        "confidence": 0.5 # Below CONFLICT_THRESHOLD
    }]

    # Execute
    new_triplets, ops = await resolve_conflicts(triplets, "user1", "turn1", mock_catalog)

    # Verify
    assert len(new_triplets) == 1
    assert len(ops) == 1
    assert ops[0]["type"] == "SUPERSEDE"
    assert ops[0]["old_object"] == "OldVal"
    assert new_triplets[0]["object"] == "NewVal"

@pytest.mark.asyncio
async def test_resolve_conflicts_exclusive_conflict(mock_catalog, mock_neo4j):
    # Setup
    triplets = [{
        "subject": "User",
        "predicate": "EXCLUSIVE_PRED",
        "object": "NewVal",
        "confidence": 0.9
    }]

    # Mock existing relationship with different value, high confidence
    mock_neo4j.query_graph.return_value = [{
        "subject": "User",
        "predicate": "EXCLUSIVE_PRED",
        "object": "OldVal",
        "turn_id": "turn0",
        "confidence": 0.9 # Above CONFLICT_THRESHOLD
    }]

    # Execute
    new_triplets, ops = await resolve_conflicts(triplets, "user1", "turn1", mock_catalog)

    # Verify
    assert len(new_triplets) == 1
    assert len(ops) == 1
    assert ops[0]["type"] == "CONFLICT"
    assert new_triplets[0]["status"] == "CONFLICTED"
