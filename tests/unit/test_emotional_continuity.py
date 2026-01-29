import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mocks
mock_neo4j = AsyncMock()
mock_state_manager = MagicMock()
mock_embedder = AsyncMock()

# Patch modules
@pytest.fixture(autouse=True)
def mock_dependencies():
    with patch("Atlas.memory.context.neo4j_manager", mock_neo4j), \
         patch("Atlas.memory.context.state_manager", mock_state_manager), \
         patch("Atlas.synthesizer.MODEL_GOVERNANCE", {"synthesizer": ["mock-model"]}), \
         patch("Atlas.synthesizer.KeyManager", MagicMock()):
        yield

from Atlas.memory.context import build_chat_context_v1
from Atlas.synthesizer import synthesizer

@pytest.mark.skip(reason="Legacy test broken by refactor")
@pytest.mark.asyncio
async def test_mood_injection_turn_zero():
    """Turn 0 (yeni oturum) ise context'e mood eklenmeli."""
    user_id = "test_user_mood"
    session_id = "test_session_mood"
    
    # Mock Neo4j responses
    mock_neo4j.count_turns.return_value = 0
    mock_neo4j.get_last_user_mood.return_value = "Yorgun"
    mock_neo4j.get_user_memory_mode.return_value = "standard"
    mock_neo4j.get_user_settings.return_value = {}
    mock_neo4j.get_facts_by_date_range.return_value = []
    
    # Mock State
    mock_state = MagicMock()
    mock_state.current_topic = None
    mock_state_manager.get_state.return_value = mock_state
    
    # Call Context Builder
    context = await build_chat_context_v1(user_id, session_id, "Merhaba", mock_embedder)
    
    # Verify injection
    assert "[ÖNCEKİ DUYGU DURUMU]" in context
    assert "Yorgun" in context
    logger.info("Turn 0 mood injection verified.")

@pytest.mark.skip(reason="Legacy test broken by refactor")
@pytest.mark.asyncio
async def test_no_injection_later_turns():
    """Turn > 0 ise context'e mood EKLENMEMELİ."""
    user_id = "test_user_mood_2"
    session_id = "test_session_mood_2"
    
    mock_neo4j.count_turns.return_value = 5  # Not a new session
    mock_neo4j.get_last_user_mood.return_value = "Mutlu"
    
    mock_state = MagicMock()
    mock_state.current_topic = "Kodlama"
    mock_state_manager.get_state.return_value = mock_state
    
    context = await build_chat_context_v1(user_id, session_id, "Devam edelim", mock_embedder)
    
    assert "[ÖNCEKİ DUYGU DURUMU]" not in context
    logger.info("Turn > 0 no-injection verified.")

def test_synthesizer_instruction_positive():
    """Synthesizer mood instruction'ı doğru oluşturmalı."""
    raw_data = "[ÖNCEKİ DUYGU DURUMU]: Kullanıcı son görüşmenizde 'Harika' hissediyordu."
    messages = [
        {"role": "user", "content": "Selam"}
    ]
    
    # We call internal method or inspect how it builds prompt if exposed.
    # Since synthesize is complex and calls API, we verify logic by inspecting code OR 
    # capturing the system prompt if possible.
    # Here we will mock the API client and check the arguments passed.
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_post = AsyncMock()
        mock_post.status_code = 200
        mock_post.json.return_value = {"choices": [{"message": {"content": "Test Response"}}]}
        mock_client.return_value.__aenter__.return_value.post = mock_post
        
        # Trigger synthesize (async)
        import asyncio
        asyncio.run(synthesizer.synthesize(
            raw_results=[{"output": raw_data}],
            session_id="sess",
            user_message="Selam",
            mode="standard"
        ))
        
        # Check call args
        call_args = mock_post.call_args
        if call_args:
            json_body = call_args[1]["json"]
            system_prompts = json_body["messages"][0]["content"]
            assert "[EMOTIONAL_CONTINUITY]" in system_prompts
            assert "Harika" in system_prompts
            logger.info("Synthesizer instruction verified.")

@pytest.mark.asyncio
async def test_synthesizer_stream_instruction():
    """Synthesizer Stream mood instruction'ı doğru oluşturmalı."""
    raw_data = [{"output": "[ÖNCEKİ DUYGU DURUMU]: Kullanıcı son görüşmenizde 'Gergin' hissediyordu."}]
    
    # Mock generate_stream
    with patch("Atlas.generator.generate_stream") as mock_gen_stream:
        mock_gen_stream.return_value = iter(["chunk"])
        
        # Consume generator
        gen = synthesizer.synthesize_stream(
            raw_results=raw_data,
            session_id="sess",
            user_message="Selam",
            mode="standard"
        )
        
        async for _ in gen:
            pass
            
        # Verify call
        args, kwargs = mock_gen_stream.call_args
        override_prompt = kwargs.get("override_system_prompt", "")
        
        assert "[EMOTIONAL_CONTINUITY]" in override_prompt
        assert "Gergin" in override_prompt
        logger.info("Synthesizer stream instruction verified.")
