
import pytest
from unittest.mock import MagicMock, AsyncMock
import sys
import importlib

# --- Mock Heavy/Problematic Dependencies Globally ---

def _register_mock(name):
    """Helper to safely register a mock in sys.modules, preserving package structure."""
    if name in sys.modules:
        return sys.modules[name]

    # If the name starts with Atlas. (but not just 'Atlas'), ensure we don't mock 'Atlas' itself
    if name.startswith('Atlas.'):
        parts = name.split('.')
        # Ensure 'Atlas' exists in sys.modules (try importing)
        if 'Atlas' not in sys.modules:
            try:
                import Atlas
            except ImportError:
                # If Atlas package is genuinely missing (e.g. not in PYTHONPATH), then mock it?
                # No, that's dangerous. Just let it fail.
                pass

        # But if we force mock something deep, we must be careful.
        # Let's avoid mocking Atlas.* if we can.
        # Instead, mock only external dependencies.
        pass

    mock = MagicMock()
    # Register the mock
    sys.modules[name] = mock

    # If it's a nested module, ensure parent has the attribute
    parts = name.split('.')
    if len(parts) > 1:
        parent_name = '.'.join(parts[:-1])
        child_name = parts[-1]

        # Ensure parent exists
        if parent_name in sys.modules:
             parent = sys.modules[parent_name]
             setattr(parent, child_name, mock)
        elif parent_name == 'Atlas':
            # Don't mock Atlas itself!
            pass
        else:
            # Recursively mock parents
            parent = _register_mock(parent_name)
            setattr(parent, child_name, mock)

    return mock

# List of EXTERNAL modules to mock
# Do NOT include 'Atlas.*' modules here unless absolutely necessary and safe.
modules_to_mock = [
    'neo4j',
    'neo4j.exceptions',
    'httpx',
    'apscheduler',
    'apscheduler.schedulers',
    'apscheduler.schedulers.asyncio',
    'apscheduler.triggers',
    'apscheduler.triggers.interval',
    'apscheduler.triggers.cron',
    'google',
    'google.genai',
    'pydantic_settings',
    'dateparser',
    'dateparser.search',
    'dotenv',
]

# Apply external mocks
for name in modules_to_mock:
    # Important: Do not overwrite existing modules if they are real packages?
    # Actually, for CI stability, overwriting might be safer if deps are missing/broken.
    # But for 'google.genai' specifically, we want to force overwrite.

    _register_mock(name)


@pytest.fixture(autouse=True)
def mock_neo4j_fixture():
    # Only try to patch if neo4j is available (mocked or real)
    if 'neo4j' in sys.modules:
        try:
            import neo4j
            mock_driver = MagicMock()
            mock_session = AsyncMock()
            mock_driver.session.return_value = mock_session
            with pytest.MonkeyPatch.context() as m:
                # Handle both real and mocked neo4j structures
                if hasattr(neo4j, 'AsyncGraphDatabase'):
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
             with pytest.MonkeyPatch.context() as m:
                if hasattr(httpx, 'AsyncClient'):
                    m.setattr("httpx.AsyncClient", MagicMock(return_value=mock_client))
                yield mock_client
        except (ImportError, AttributeError):
             yield MagicMock()
    else:
        yield MagicMock()
