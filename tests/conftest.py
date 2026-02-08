
import pytest
from unittest.mock import MagicMock, AsyncMock
import sys
import datetime
import importlib

# --- Mock Heavy/Problematic Dependencies Globally ---

def _register_mock(name):
    """Helper to safely register a mock in sys.modules, preserving package structure."""
    if name in sys.modules:
        return sys.modules[name]

    # If the name starts with Atlas. (but not just 'Atlas'), ensure we don't mock 'Atlas' itself
    if name.startswith('Atlas.'):
        parts = name.split('.')
        if 'Atlas' not in sys.modules:
            try:
                import Atlas
            except ImportError:
                pass
        pass

    mock = MagicMock()
    sys.modules[name] = mock

    parts = name.split('.')
    if len(parts) > 1:
        parent_name = '.'.join(parts[:-1])
        child_name = parts[-1]

        if parent_name in sys.modules:
             parent = sys.modules[parent_name]
             setattr(parent, child_name, mock)
        elif parent_name == 'Atlas':
            pass
        else:
            parent = _register_mock(parent_name)
            setattr(parent, child_name, mock)

    return mock

# ALWAYS mock these (problematic/heavy deps even if present)
forced_mocks = [
    'google.genai',
]

# Mock these only if MISSING
conditional_mocks = [
    'neo4j',
    'neo4j.exceptions',
    'httpx',
    'apscheduler',
    'apscheduler.schedulers',
    'apscheduler.schedulers.asyncio',
    'apscheduler.triggers',
    'apscheduler.triggers.interval',
    'apscheduler.triggers.cron',
    'qdrant_client',
    'qdrant_client.models',
    'pydantic_settings',
    'dateparser',
    'dateparser.search',
    'dotenv',
]

# Apply mocks
for name in forced_mocks:
    _register_mock(name)

for name in conditional_mocks:
    if name not in sys.modules:
        # Check if importable
        try:
            importlib.import_module(name)
        except ImportError:
            _register_mock(name)

# --- Configure Mocks with Sane Defaults ---

# Configure dateparser.search.search_dates to return a valid list or None
if 'dateparser.search' in sys.modules and isinstance(sys.modules['dateparser.search'], MagicMock):
    # Return a dummy date for tests that expect date parsing
    sys.modules['dateparser.search'].search_dates.return_value = [('yesterday', datetime.datetime.now())]

@pytest.fixture(autouse=True)
def mock_neo4j_fixture():
    # Setup mocks for Neo4j if it is mocked
    if 'neo4j' in sys.modules:
        try:
            import neo4j
            # Check if it's a real module or a mock
            if isinstance(neo4j, MagicMock) or getattr(neo4j, '__file__', None) is None:
                 # It's likely our mock or a system mock
                 mock_driver = MagicMock()
                 mock_session = AsyncMock()
                 mock_driver.session.return_value = mock_session
                 with pytest.MonkeyPatch.context() as m:
                    if hasattr(neo4j, 'AsyncGraphDatabase'):
                        m.setattr("neo4j.AsyncGraphDatabase.driver", MagicMock(return_value=mock_driver))
                    yield mock_driver
            else:
                 # Real neo4j module, let it be (or mock driver if needed for tests)
                 # We usually want to mock the driver even if the package exists
                 mock_driver = MagicMock()
                 mock_session = AsyncMock()
                 mock_driver.session.return_value = mock_session
                 with pytest.MonkeyPatch.context() as m:
                    m.setattr("neo4j.AsyncGraphDatabase.driver", MagicMock(return_value=mock_driver))
                    yield mock_driver
        except (ImportError, AttributeError):
            yield MagicMock()
    else:
        yield MagicMock()

@pytest.fixture(autouse=True)
def mock_httpx_fixture():
    if 'httpx' in sys.modules:
        try:
             import httpx
             mock_client = AsyncMock()

             # Configure standard response structure to avoid coroutine warnings
             # and simulate sync methods correctly
             mock_response = AsyncMock()
             mock_response.raise_for_status = MagicMock()
             mock_response.json = MagicMock(return_value={})

             mock_client.post.return_value = mock_response
             mock_client.get.return_value = mock_response
             mock_client.put.return_value = mock_response
             mock_client.delete.return_value = mock_response

             with pytest.MonkeyPatch.context() as m:
                if hasattr(httpx, 'AsyncClient'):
                    m.setattr("httpx.AsyncClient", MagicMock(return_value=mock_client))
                yield mock_client
        except (ImportError, AttributeError):
             yield MagicMock()
    else:
        yield MagicMock()

# Ensure Atlas.config is loaded for tests that need to reload it
@pytest.fixture(autouse=True)
def ensure_config_loaded():
    try:
        import Atlas.config
    except ImportError:
        pass

# Global Neo4j Manager Mock Fix
@pytest.fixture(autouse=True)
def patch_neo4j_manager_methods():
    """Ensure Neo4j manager methods return usable values (ints, lists) instead of just Mocks."""
    with pytest.MonkeyPatch.context() as m:
        try:
            from Atlas.memory.neo4j_manager import neo4j_manager

            # Patch count_turns to return 0 (int) - Corrected method name
            m.setattr(neo4j_manager, 'count_turns', AsyncMock(return_value=0), raising=False)

            # Patch fact_exists to return False (bool)
            m.setattr(neo4j_manager, 'fact_exists', AsyncMock(return_value=False), raising=False)

            # Patch query_graph to return empty list (list)
            m.setattr(neo4j_manager, 'query_graph', AsyncMock(return_value=[]), raising=False)

            # Patch try_acquire_lock to return True (bool)
            m.setattr(neo4j_manager, 'try_acquire_lock', AsyncMock(return_value=True), raising=False)

            # Patch release_lock to return None
            m.setattr(neo4j_manager, 'release_lock', AsyncMock(return_value=None), raising=False)

            # Patch get_session_topic to return "general" or similar string
            m.setattr(neo4j_manager, 'get_session_topic', AsyncMock(return_value="general"), raising=False)

        except ImportError:
            pass
        yield
