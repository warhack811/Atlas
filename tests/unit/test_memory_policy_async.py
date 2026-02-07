import pytest
import os
from unittest.mock import AsyncMock, patch
from Atlas.memory.memory_policy import load_policy_for_user, POLICY_STANDARD, POLICY_FULL, POLICY_OFF

@pytest.mark.asyncio
async def test_load_policy_for_user_from_neo4j():
    """Neo4j'den gelen moda göre doğru politikanın yüklendiğini doğrula."""
    user_id = "test_user_neo4j"

    with patch("Atlas.memory.neo4j_manager.neo4j_manager.get_user_memory_mode", new_callable=AsyncMock) as mock_get_mode:
        # 1. FULL mode testi
        mock_get_mode.return_value = "FULL"
        policy = await load_policy_for_user(user_id)
        assert policy.mode == "FULL"
        assert policy.thresholds["utility"] == 0.4

        # 2. OFF mode testi
        mock_get_mode.return_value = "OFF"
        policy = await load_policy_for_user(user_id)
        assert policy.mode == "OFF"
        assert policy.write_enabled is False

        # 3. Bilinmeyen/Default mode testi
        mock_get_mode.return_value = "STANDARD"
        policy = await load_policy_for_user(user_id)
        assert policy.mode == "STANDARD"

@pytest.mark.asyncio
async def test_load_policy_for_user_fallback_env():
    """Neo4j'den veri gelmediğinde environment variable fallback'ini doğrula."""
    user_id = "test_user_env"

    with patch("Atlas.memory.neo4j_manager.neo4j_manager.get_user_memory_mode", new_callable=AsyncMock) as mock_get_mode:
        mock_get_mode.return_value = None # Neo4j'de kayıt yok

        with patch.dict(os.environ, {"ATLAS_DEFAULT_MEMORY_MODE": "FULL"}):
            policy = await load_policy_for_user(user_id)
            assert policy.mode == "FULL"

        with patch.dict(os.environ, {"ATLAS_DEFAULT_MEMORY_MODE": "OFF"}):
            policy = await load_policy_for_user(user_id)
            assert policy.mode == "OFF"

@pytest.mark.asyncio
async def test_load_policy_for_user_exception_fallback():
    """Neo4j hatası durumunda fallback yapıldığını doğrula."""
    user_id = "test_user_error"

    with patch("Atlas.memory.neo4j_manager.neo4j_manager.get_user_memory_mode", side_effect=Exception("Neo4j down")):
        with patch.dict(os.environ, {"ATLAS_DEFAULT_MEMORY_MODE": "STANDARD"}):
            policy = await load_policy_for_user(user_id)
            assert policy.mode == "STANDARD"
