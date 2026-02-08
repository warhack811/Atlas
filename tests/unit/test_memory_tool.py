import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from Atlas.tools.registry import ToolRegistry
from Atlas.tools.handlers.memory_tool import MemoryTool

@pytest.fixture
def mock_neo4j_manager():
    mock = AsyncMock()
    with patch("Atlas.tools.handlers.memory_tool.neo4j_manager", mock):
        yield mock

@pytest.mark.asyncio
async def test_memory_tool_execution(mock_neo4j_manager):
    tool = MemoryTool()

    # Mock graph query response
    mock_neo4j_manager.query_graph.return_value = [
        {"subject": "Kullanıcı", "predicate": "MESLEĞİ", "object": "Mühendis"},
        {"subject": "Kullanıcı", "predicate": "YAŞAR_YER", "object": "Ankara"}
    ]

    result = await tool.execute(query="meslek")

    assert result["source"] == "memory"
    assert "Mühendis" in result["content"]
    assert "Ankara" in result["content"]

    # Verify query params
    mock_neo4j_manager.query_graph.assert_called_once()
    call_args = mock_neo4j_manager.query_graph.call_args
    # The second argument to query_graph is the params dict
    # call_args[0] are positional args: (query_str, params_dict)

    # Check if params passed as positional arg 2
    if len(call_args[0]) > 1:
        assert call_args[0][1]["q"] == "meslek"
    else:
        # Or kwargs
        assert call_args[1]["q"] == "meslek"

@pytest.mark.asyncio
async def test_memory_tool_empty_result(mock_neo4j_manager):
    tool = MemoryTool()
    mock_neo4j_manager.query_graph.return_value = []

    result = await tool.execute(query="bilinmeyen")
    assert "bulunamadı" in result["result"]

def test_registry_integration():
    registry = ToolRegistry()
    registry.register_tool("retrieve_memory", MemoryTool())

    tool = registry.get_tool("retrieve_memory")
    assert isinstance(tool, MemoryTool)
    assert tool.name == "retrieve_memory"

    schema = tool.to_openai_function()
    assert schema["function"]["name"] == "retrieve_memory"
    assert "query" in schema["function"]["parameters"]["properties"]
