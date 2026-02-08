import pytest
from unittest.mock import MagicMock, AsyncMock, patch, call
from Atlas.synthesizer import Synthesizer
from Atlas.config import API_CONFIG

# Mock dependencies
@pytest.fixture
def mock_key_manager():
    with patch("Atlas.synthesizer.KeyManager") as mock:
        mock.get_best_key.return_value = "dummy_key"
        yield mock

@pytest.fixture
def mock_message_buffer():
    # Patching in Atlas.synthesizer because it is imported at top-level there
    with patch("Atlas.synthesizer.MessageBuffer") as mock:
        mock.get_llm_messages.return_value = [
            {"role": "user", "content": "previous message"},
            {"role": "assistant", "content": "previous response"}
        ]
        yield mock

@pytest.fixture
def mock_style_injector():
    # Patching in Atlas.synthesizer because it is imported at top-level there
    with patch("Atlas.synthesizer.get_system_instruction") as mock:
        mock.return_value = "System Instruction"
        yield mock

@pytest.fixture
def mock_generate_stream():
    # Patching in Atlas.synthesizer because it is imported at top-level there
    with patch("Atlas.synthesizer.generate_stream") as mock:
        async def async_gen(*args, **kwargs):
            yield "chunk1"
            yield "chunk2"
        mock.side_effect = async_gen
        yield mock

# Define local mock_httpx fixture if not available globally or to ensure it works
@pytest.fixture
def mock_httpx_local():
    with patch("httpx.AsyncClient") as mock:
        yield mock

@pytest.mark.asyncio
async def test_synthesize_basic(mock_key_manager, mock_message_buffer, mock_style_injector, mock_httpx_local):
    mock_httpx = mock_httpx_local
    # Ensure client context manager returns the client itself
    mock_instance = mock_httpx.return_value
    mock_instance.__aenter__.return_value = mock_instance

    # Setup mock_httpx response for synthesize
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Synthesized Response"}}]
    }

    # httpx.post is async, so it must return an awaitable that yields the response
    async def mock_post(*args, **kwargs):
        return mock_response

    mock_instance.post.side_effect = mock_post

    raw_results = [{"model": "expert1", "output": "Expert Output 1"}]
    result, model, prompt, metadata = await Synthesizer.synthesize(
        raw_results, "session1", "general", "User Message"
    )

    assert result == "Synthesized Response"
    assert "Expert Output 1" in prompt

    # Check if system prompt contains instructions
    # Synthesizer sends messages list to httpx.post
    call_args = mock_instance.post.call_args
    assert call_args is not None
    messages = call_args[1]['json']['messages']
    system_msg = next(m for m in messages if m['role'] == 'system')
    assert "System Instruction" in system_msg['content']

@pytest.mark.asyncio
async def test_synthesize_mirroring(mock_key_manager, mock_message_buffer, mock_style_injector, mock_httpx_local):
    mock_httpx = mock_httpx_local
    # Ensure client context manager returns the client itself
    mock_instance = mock_httpx.return_value
    mock_instance.__aenter__.return_value = mock_instance

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Response"}}]
    }

    # httpx.post is async
    async def mock_post(*args, **kwargs):
        return mock_response

    mock_instance.post.side_effect = mock_post

    # "yorgun" triggers mirroring
    await Synthesizer.synthesize(
        [], "session1", "general", "Ben çok yorgun hissediyorum"
    )

    call_args = mock_instance.post.call_args
    messages = call_args[1]['json']['messages']
    system_msg = next(m for m in messages if m['role'] == 'system')
    assert "[MIRRORING]" in system_msg['content']
    assert "yorgun" in system_msg['content']

@pytest.mark.asyncio
async def test_synthesize_stream_basic(mock_key_manager, mock_message_buffer, mock_style_injector, mock_generate_stream):
    raw_results = [{"model": "expert1", "output": "Expert Output 1"}]

    chunks = []
    async for chunk in Synthesizer.synthesize_stream(
        raw_results, "session1", "general", "User Message"
    ):
        chunks.append(chunk)

    assert len(chunks) == 3 # metadata, chunk1, chunk2
    assert chunks[0]["type"] == "metadata"
    assert chunks[1]["content"] == "chunk1"

    # Verify generate_stream called with correct prompt
    call_args = mock_generate_stream.call_args
    prompt = call_args[0][0] # first arg is prompt
    override_system = call_args[1]['override_system_prompt']

    assert "Expert Output 1" in prompt
    assert "System Instruction" in override_system
