import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from Atlas.tools.handlers.web_search import WebSearchTool
import httpx

@pytest.mark.asyncio
async def test_web_search_success():
    """Test successful web search execution."""
    tool = WebSearchTool()

    # Mock Config.SERPER_API_KEY
    with patch("Atlas.config.Config.SERPER_API_KEY", "dummy_key"):

        # Configure response mock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "organic": [
                {"title": "Result 1", "link": "http://example.com/1", "snippet": "Description 1"},
                {"title": "Result 2", "link": "http://example.com/2", "snippet": "Description 2"}
            ],
            "knowledgeGraph": {
                "title": "Knowledge",
                "description": "Details",
                "attributes": {"Type": "Test"}
            }
        }
        mock_response.raise_for_status = MagicMock()

        # Mock httpx client
        mock_client = AsyncMock()

        # The key is here: The call `await client.post(...)` returns `mock_response`.
        # So client.post should be an AsyncMock that returns mock_response.
        mock_client.post.return_value = mock_response

        # We need to mock the CONTEXT MANAGER `async with httpx.AsyncClient() as client`
        # This means httpx.AsyncClient(...) should return an object whose __aenter__ returns mock_client.

        mock_client_context = AsyncMock()
        mock_client_context.__aenter__.return_value = mock_client
        mock_client_context.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client_context):
            result = await tool.execute(query="test query")

            assert result.get("source") == "google_serper"
            assert result.get("results_count") == 2
            assert "**Knowledge**" in result.get("content", "")
            assert "- [Result 1](http://example.com/1): Description 1" in result.get("content", "")

@pytest.mark.asyncio
async def test_web_search_missing_api_key():
    """Test execution without API key."""
    tool = WebSearchTool()

    with patch("Atlas.config.Config.SERPER_API_KEY", ""):
        result = await tool.execute(query="test")
        assert "error" in result
        assert "API anahtarı yapılandırılmamış" in result["error"]

@pytest.mark.asyncio
async def test_web_search_api_error():
    """Test handling of API errors."""
    tool = WebSearchTool()

    with patch("Atlas.config.Config.SERPER_API_KEY", "dummy_key"):

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        def raise_error():
            raise httpx.HTTPStatusError("Error", request=MagicMock(), response=mock_response)

        mock_response.raise_for_status.side_effect = raise_error

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        mock_client_context = AsyncMock()
        mock_client_context.__aenter__.return_value = mock_client
        mock_client_context.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client_context):
            result = await tool.execute(query="test")
            assert "error" in result
            assert "Arama servisi hatası: 500" in result["error"]
