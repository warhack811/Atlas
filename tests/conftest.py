import pytest
from unittest.mock import MagicMock, AsyncMock
import sys

@pytest.fixture(autouse=True)
def mock_neo4j():
    if 'neo4j' not in sys.modules:
        sys.modules['neo4j'] = MagicMock()

    with pytest.MonkeyPatch.context() as m:
        try:
            import neo4j
            mock_driver = MagicMock()
            mock_session = AsyncMock()
            mock_driver.session.return_value = mock_session
            m.setattr("neo4j.AsyncGraphDatabase.driver", MagicMock(return_value=mock_driver))
            yield mock_driver
        except (ImportError, AttributeError):
            yield MagicMock()

@pytest.fixture(autouse=True)
def mock_httpx():
    if 'httpx' not in sys.modules:
        sys.modules['httpx'] = MagicMock()

    with pytest.MonkeyPatch.context() as m:
        try:
            import httpx
            mock_client = AsyncMock()
            m.setattr("httpx.AsyncClient", MagicMock(return_value=mock_client))
            yield mock_client
        except (ImportError, AttributeError):
            yield MagicMock()
