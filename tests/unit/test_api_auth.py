
import pytest
import sys
from unittest.mock import MagicMock, patch

# Mock all the heavy modules to avoid import errors and side effects
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

@pytest.mark.asyncio
async def test_get_current_user_behavior():
    # Use patch.dict to mock sys.modules only within this test function context
    with patch.dict(sys.modules, modules_to_mock):
        # Import the module under test INSIDE the patch context
        # We need to reload it or ensure it's not already loaded to pick up the mocks?
        # If Atlas.api is already loaded, these mocks won't affect its imports if they are top-level.
        # But Atlas.api imports are top-level.
        # So if Atlas.api was imported by another test before, this might be tricky.
        # However, for this specific test, we want to isolate it.

        # If we import Atlas.api here, it will use the mocked modules.
        # But we need to make sure we don't pollute the global sys.modules permanently.
        # patch.dict handles restoration.

        # We also need to be careful about double import if it's already in sys.modules.
        # If it is, we might need to reload it, or just patch the specific things we need.

        # Since we are mocking SO MANY things, maybe we should just mock the specific function
        # that get_current_user relies on, if possible?
        # get_current_user uses: Cookie, decode_session_token.
        # It is in Atlas.api.

        # If we can import Atlas.api without crashing, we are good.
        # The crash comes from importing heavy modules at top level of Atlas.api.

        # Let's try to import inside the patch.
        import importlib
        if "Atlas.api" in sys.modules:
             # If it's already loaded, we might need to reload it to use our mocks?
             # Or maybe not, if we just want to test the function.
             # If it's loaded, we can just use it.
             from Atlas.api import get_current_user
        else:
             from Atlas.api import get_current_user

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
