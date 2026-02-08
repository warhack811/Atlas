
import pytest
import sys
import importlib
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.fixture
def lifecycle_engine_module():
    # Mock dependencies before import
    mock_neo4j_manager_module = MagicMock()
    mock_neo4j_manager_instance = AsyncMock()
    mock_neo4j_manager_module.neo4j_manager = mock_neo4j_manager_instance

    mock_config_module = MagicMock()
    mock_config_module.Config = MagicMock()
    mock_config_module.MEMORY_CONFIDENCE_SETTINGS = {"CONFLICT_THRESHOLD": 0.7}

    modules_to_patch = {
        'Atlas.memory.neo4j_manager': mock_neo4j_manager_module,
        'Atlas.config': mock_config_module,
        'dateparser': MagicMock(),
        'dateparser.search': MagicMock(),
        'neo4j': MagicMock(),
        # Do NOT mock pydantic globally as it breaks other tests (fastapi)
        # 'pydantic': MagicMock(),
        # 'pydantic_settings': MagicMock()
    }

    with patch.dict(sys.modules, modules_to_patch):
        # Import inside the patch context
        if 'Atlas.memory.lifecycle_engine' in sys.modules:
            importlib.reload(sys.modules['Atlas.memory.lifecycle_engine'])
        else:
            importlib.import_module('Atlas.memory.lifecycle_engine')

        yield sys.modules['Atlas.memory.lifecycle_engine']

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
def mock_neo4j(lifecycle_engine_module):
    # Access the mock injected into sys.modules
    return sys.modules['Atlas.memory.neo4j_manager'].neo4j_manager

@pytest.mark.asyncio
async def test_resolve_conflicts_exclusive_no_existing(lifecycle_engine_module, mock_catalog, mock_neo4j):
    resolve_conflicts = lifecycle_engine_module.resolve_conflicts

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
async def test_resolve_conflicts_exclusive_existing_same(lifecycle_engine_module, mock_catalog, mock_neo4j):
    resolve_conflicts = lifecycle_engine_module.resolve_conflicts

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
async def test_resolve_conflicts_exclusive_existing_different_supersede(lifecycle_engine_module, mock_catalog, mock_neo4j):
    resolve_conflicts = lifecycle_engine_module.resolve_conflicts

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
async def test_resolve_conflicts_exclusive_conflict(lifecycle_engine_module, mock_catalog, mock_neo4j):
    resolve_conflicts = lifecycle_engine_module.resolve_conflicts

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
