import pytest
from unittest.mock import MagicMock, AsyncMock

@pytest.fixture(autouse=True)
def mock_neo4j():
    with pytest.MonkeyPatch.context() as m:
        mock_driver = MagicMock()
        mock_session = AsyncMock()
        mock_driver.session.return_value = mock_session
        m.setattr("neo4j.AsyncGraphDatabase.driver", MagicMock(return_value=mock_driver))
        yield mock_driver

@pytest.fixture(autouse=True)
def mock_httpx():
    with pytest.MonkeyPatch.context() as m:
        mock_client = AsyncMock()
        m.setattr("httpx.AsyncClient", MagicMock(return_value=mock_client))
        yield mock_client
