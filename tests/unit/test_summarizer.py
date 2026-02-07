import json
from Atlas.tools.summarizer import summarize_tool_output

def test_summarize_short_string():
    """Verify input shorter than max_chars returns identically."""
    input_str = "Short string"
    assert summarize_tool_output("test_tool", input_str, max_chars=100) == input_str

def test_summarize_long_string():
    """Verify input longer than max_chars is truncated and appended with '...'."""
    input_str = "A" * 100
    max_chars = 50
    result = summarize_tool_output("test_tool", input_str, max_chars=max_chars)
    assert len(result) == max_chars + 3
    assert result == "A" * max_chars + "..."

def test_summarize_json_list():
    """Verify JSON list input returns the first 3 elements as a JSON string."""
    data = [1, 2, 3, 4, 5]
    input_str = json.dumps(data)
    # Set max_chars low enough to trigger summarization
    result = summarize_tool_output("test_tool", input_str, max_chars=10)
    parsed_result = json.loads(result)
    assert isinstance(parsed_result, list)
    assert len(parsed_result) == 3
    assert parsed_result == [1, 2, 3]

def test_summarize_json_dict():
    """Verify JSON dict input returns a JSON string containing only allowed keys."""
    data = {
        "title": "Test Title",
        "snippet": "Test Snippet",
        "link": "http://example.com",
        "content": "Test Content",
        "summary": "Test Summary",
        "extra": "Extra Info",
        "another": "Another Info"
    }
    input_str = json.dumps(data)
    # Set max_chars low enough to trigger summarization
    result = summarize_tool_output("test_tool", input_str, max_chars=50)
    parsed_result = json.loads(result)
    assert isinstance(parsed_result, dict)
    assert "title" in parsed_result
    assert "extra" not in parsed_result
    # Only "title", "snippet", "link", "content", "summary" should be kept (5 items)
    assert len(parsed_result) == 5

def test_summarize_invalid_json():
    """Verify invalid JSON input falls back to string truncation."""
    input_str = "{invalid_json: true" + "A" * 100
    max_chars = 50
    result = summarize_tool_output("test_tool", input_str, max_chars=max_chars)
    assert result.endswith("...")
    assert len(result) == max_chars + 3

def test_summarize_json_primitive():
    """Verify JSON input that is not a list or dict falls back to string truncation behavior."""
    # "123" is valid JSON, but not list or dict
    input_str = "123" * 50
    max_chars = 10
    result = summarize_tool_output("test_tool", input_str, max_chars=max_chars)
    # The code: tries json.loads -> succeeds -> checks list (False) -> checks dict (False) -> exits try -> returns truncated
    assert result == input_str[:max_chars] + "..."

def test_summarize_empty_input():
    """Verify empty string input returns empty string."""
    assert summarize_tool_output("test_tool", "") == ""

def test_custom_max_chars():
    """Verify the max_chars parameter works as expected."""
    input_str = "ABCDE"
    assert summarize_tool_output("test_tool", input_str, max_chars=3) == "ABC..."
    assert summarize_tool_output("test_tool", input_str, max_chars=10) == "ABCDE"
