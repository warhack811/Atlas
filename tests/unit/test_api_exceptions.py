
import pytest
import sys
import asyncio
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

# Mock all the heavy modules
modules_to_mock = {
    "Atlas.memory.semantic_cache": MagicMock(),
    "Atlas.memory.text_normalize": MagicMock(),
    "Atlas.rdr": MagicMock(),
    "Atlas.scheduler": MagicMock(),
    "Atlas.memory": MagicMock(),
    "Atlas.orchestrator": MagicMock(),
    "Atlas.dag_executor": MagicMock(),
    "Atlas.synthesizer": MagicMock(),
    "Atlas.safety": MagicMock(),
    "Atlas.memory.neo4j_manager": MagicMock(),
    "Atlas.memory.request_context": MagicMock(),
    "Atlas.memory.trace": MagicMock(),
    "Atlas.time_context": MagicMock(),
    "Atlas.quality": MagicMock(),
    "Atlas.memory.extractor": MagicMock(),
    "Atlas.key_manager": MagicMock(),
    "Atlas.memory.qdrant_manager": MagicMock(),
    "Atlas.observer": MagicMock(),
    "Atlas.memory.prospective_store": MagicMock(),
    "Atlas.memory.context": MagicMock(),
    "Atlas.benchmark": MagicMock(),
    "Atlas.benchmark.store": MagicMock(),
    "Atlas.vision_engine": MagicMock(),
    "Atlas.reasoning_pool": MagicMock(),
    "Atlas.memory.predicate_catalog": MagicMock(),
}

# We need to ensure neo4j.exceptions are available for the test
# Since we are testing exception handling specifically for them.
# The real neo4j module might be needed or we can mock it but we need the exceptions to be importable.
# If the environment has neo4j installed, we use it. If not, we must mock it carefully.
try:
    import neo4j
    from neo4j.exceptions import ServiceUnavailable, SessionExpired
except ImportError:
    # Create mock exceptions if neo4j is not installed
    class ServiceUnavailable(Exception): pass
    class SessionExpired(Exception): pass

    mock_neo4j = MagicMock()
    mock_neo4j.exceptions.ServiceUnavailable = ServiceUnavailable
    mock_neo4j.exceptions.SessionExpired = SessionExpired
    modules_to_mock["neo4j"] = mock_neo4j
    modules_to_mock["neo4j.exceptions"] = mock_neo4j.exceptions

@pytest.mark.asyncio
async def test_get_current_user_optional():
    with patch.dict(sys.modules, modules_to_mock):
        # Import inside the patch
        from Atlas.api import get_current_user_optional

        # Patch decode_session_token
        with patch("Atlas.api.decode_session_token") as mock_decode:
            # 1. Valid Token
            mock_decode.return_value = {"username": "test"}
            result = await get_current_user_optional("valid_token")
            assert result == {"username": "test"}

            # 2. None Token
            result = await get_current_user_optional(None)
            assert result is None

            # 3. Invalid Token (Raises Exception)
            mock_decode.side_effect = Exception("Invalid token")
            result = await get_current_user_optional("invalid_token")
            assert result is None  # Should return None, not raise

@pytest.mark.asyncio
async def test_chat_exception_handling():
    with patch.dict(sys.modules, modules_to_mock):
        from Atlas.api import chat, ChatRequest
        from neo4j.exceptions import ServiceUnavailable

        # Mock dependencies
        mock_user = {"username": "test_user", "role": "user"}
        mock_bg_tasks = MagicMock()

        # Create a request
        request = ChatRequest(message="hello", session_id="test_session")

        # Mock functions called inside chat to raise ServiceUnavailable
        # The first thing it does is check safety, then RDR create, then...
        # Let's mock 'Atlas.config.is_user_whitelisted' to return True
        # And 'Atlas.safety.safety_gate.check_input_safety' to return True

        with patch("Atlas.config.is_user_whitelisted", return_value=True), \
             patch("Atlas.safety.safety_gate.check_input_safety", new_callable=AsyncMock) as mock_safety, \
             patch("Atlas.memory.neo4j_manager.neo4j_manager.ensure_user_session", side_effect=ServiceUnavailable("DB Down")):

            mock_safety.return_value = (True, "hello", [], "test_model")

            # This should raise HTTPException 503
            with pytest.raises(HTTPException) as excinfo:
                await chat(request, mock_bg_tasks, user=mock_user)

            assert excinfo.value.status_code == 503
            assert "Veritabanı servisine erişilemiyor" in excinfo.value.detail

# Helper for AsyncMock if not available in unittest.mock (older python)
# But we are in a modern environment.
from unittest.mock import AsyncMock

if __name__ == "__main__":
    asyncio.run(test_get_current_user_optional())
    asyncio.run(test_chat_exception_handling())
    print("Tests passed!")
