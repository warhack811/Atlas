
import pytest
import sys
from unittest.mock import MagicMock, patch

# Mock all the heavy modules to avoid import errors and side effects
modules_to_mock = [
    "Atlas.memory.semantic_cache",
    "Atlas.memory.text_normalize",
    "Atlas.rdr",
    "Atlas.scheduler",
    "Atlas.memory",
    "Atlas.orchestrator",
    "Atlas.dag_executor",
    "Atlas.synthesizer",
    "Atlas.safety",
    "Atlas.memory.neo4j_manager",
    "Atlas.memory.request_context",
    "Atlas.memory.trace",
    "Atlas.time_context",
    "Atlas.quality",
    "Atlas.memory.extractor",
    "Atlas.key_manager",
    "Atlas.memory.qdrant_manager",
    "Atlas.observer",
    "Atlas.memory.prospective_store",
    "Atlas.memory.context",
    "Atlas.benchmark",
    "Atlas.benchmark.store",
    "Atlas.vision_engine",
    "Atlas.reasoning_pool",
    "Atlas.memory.predicate_catalog",
]

for module in modules_to_mock:
    sys.modules[module] = MagicMock()

# Import the module under test
# We verify Atlas.api.decode_session_token is what we patch
from Atlas.api import get_current_user

@pytest.mark.asyncio
async def test_get_current_user_behavior():
    # Patch where it is looked up: inside Atlas.api
    with patch("Atlas.api.decode_session_token") as mock_decode:
        # Case 1: Session is None (Missing cookie)
        # Note: get_current_user(None) means atlas_session=None.
        # It returns None immediately without calling decode_session_token.
        assert await get_current_user(None) is None
        mock_decode.assert_not_called()

        # Case 2: Session is valid
        mock_decode.return_value = {"username": "test", "role": "user"}
        assert await get_current_user("valid_token") == {"username": "test", "role": "user"}
        mock_decode.assert_called_with("valid_token")

        # Case 3: Session is invalid (decode returns None)
        mock_decode.return_value = None
        assert await get_current_user("invalid_token") is None

if __name__ == "__main__":
    # Manually run the async tests if executed as script
    import asyncio
    asyncio.run(test_get_current_user_behavior())
    print("Tests passed!")
