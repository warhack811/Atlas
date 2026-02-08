import pytest
from typing import Type
from pydantic import BaseModel
from Atlas.tools.base import BaseTool

# Define a mock input schema
class MockInputSchema(BaseModel):
    query: str
    limit: int = 10

# Define a concrete subclass for testing
class MockTool(BaseTool):
    name = "mock_tool"
    description = "A mock tool for testing"
    input_schema = MockInputSchema

    async def execute(self, **kwargs):
        return f"Executed with {kwargs}"

@pytest.mark.asyncio
async def test_base_tool_instantiation():
    """Verify that a subclass can be instantiated and attributes are accessible."""
    tool = MockTool()
    assert tool.name == "mock_tool"
    assert tool.description == "A mock tool for testing"
    assert tool.input_schema == MockInputSchema

@pytest.mark.asyncio
async def test_to_openai_function():
    """Verify that to_openai_function returns the correct JSON schema."""
    tool = MockTool()
    schema = tool.to_openai_function()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "mock_tool"
    assert schema["function"]["description"] == "A mock tool for testing"

    parameters = schema["function"]["parameters"]
    assert "properties" in parameters
    assert "query" in parameters["properties"]
    assert "limit" in parameters["properties"]
    assert "required" in parameters
    assert "query" in parameters["required"]

@pytest.mark.asyncio
async def test_execute():
    """Verify that the execute method works as expected."""
    tool = MockTool()
    result = await tool.execute(query="test", limit=5)
    assert result == "Executed with {'query': 'test', 'limit': 5}"

def test_instantiation_enforces_abstract_methods():
    """Verify that a subclass without execute implementation raises a TypeError."""
    class IncompleteTool(BaseTool):
        name = "incomplete_tool"
        description = "This tool is incomplete"
        input_schema = MockInputSchema

        # Missing execute implementation

    with pytest.raises(TypeError):
        IncompleteTool()
