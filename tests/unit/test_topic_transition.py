import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from Atlas.synthesizer import Synthesizer

@pytest.mark.asyncio
async def test_synthesizer_topic_transition_injection():
    """Synthesizer'a yeni konu geldiğinde [KONU DEĞİŞİMİ] talimatının eklendiğini doğrula."""
    # Mocking httpx.AsyncClient.post
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Test yanıtı"}}]
        }
        mock_post.return_value = mock_response

        # Test parametreleri
        raw_results = [{"model": "expert-1", "output": "Test veri"}]
        session_id = "test_sess_trans"
        current_topic = "Nükleer Fizik"

        # Sentezleyiciyi çağır
        with patch("Atlas.key_manager.KeyManager.get_best_key", return_value="dummy_key"):
            with patch("Atlas.memory.buffer.MessageBuffer.get_llm_messages", return_value=[]):
                await Synthesizer.synthesize(
                    raw_results, session_id, current_topic=current_topic
                )

        # Call parameters check
        call_args = mock_post.return_value.call_args
        if call_args is None:
             # Fallback if return_value mock isn't called directly (depends on httpx usage)
             # But here we mocked the class method, so instances are mocks.
             # Wait, httpx.AsyncClient() context manager returns the client.
             # So 'mock_post' IS the class mock.
             # We need to capture the instance returned by __aenter__
             pass

        # Since we mocked the CLASS method 'post', and it's an async context manager in usage:
        # async with httpx.AsyncClient(...) as client:
        #    client.post(...)
        # We need to patch "httpx.AsyncClient" class to return a mock client
        # OR patch "httpx.AsyncClient.post" directly if the code uses it directly (it does client.post)

    # Correct approach: Patch the class so instance.post works
    with patch("httpx.AsyncClient", new_callable=MagicMock) as mock_client_cls:
        mock_instance = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_instance

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"message": {"content": "Test"}}]}
        mock_instance.post.return_value = mock_response

        # Test params
        raw_results = [{"model": "expert-1", "output": "Test veri"}]
        session_id = "test_sess_trans"
        current_topic = "Nükleer Fizik"

        with patch("Atlas.key_manager.KeyManager.get_best_key", return_value="dummy_key"):
            with patch("Atlas.memory.buffer.MessageBuffer.get_llm_messages", return_value=[]):
                await Synthesizer.synthesize(
                    raw_results, session_id, current_topic=current_topic
                )

        call_args = mock_instance.post.call_args
        json_data = call_args.kwargs["json"]
        system_prompt = json_data["messages"][0]["content"]

        assert "[KONU DEĞİŞİMİ]" in system_prompt
        assert "'Nükleer Fizik'" in system_prompt

@pytest.mark.asyncio
async def test_synthesizer_no_transition_on_same():
    """'SAME' geldiğinde [KONU DEĞİŞİMİ] talimatının EKLENMEDİĞİNİ doğrula."""
    with patch("httpx.AsyncClient", new_callable=MagicMock) as mock_client_cls:
        mock_instance = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_instance

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"message": {"content": "Test"}}]}
        mock_instance.post.return_value = mock_response

        with patch("Atlas.key_manager.KeyManager.get_best_key", return_value="dummy_key"):
            with patch("Atlas.memory.buffer.MessageBuffer.get_llm_messages", return_value=[]):
                await Synthesizer.synthesize(
                    [{"model": "x", "output": "y"}], "test", current_topic="SAME"
                )

        system_prompt = mock_instance.post.call_args.kwargs["json"]["messages"][0]["content"]
        assert "[KONU DEĞİŞİMİ]" not in system_prompt

@pytest.mark.asyncio
async def test_synthesizer_no_transition_on_none():
    """Konu None geldiğinde talimatın eklenmediğini doğrula."""
    with patch("httpx.AsyncClient", new_callable=MagicMock) as mock_client_cls:
        mock_instance = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_instance

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"message": {"content": "Test"}}]}
        mock_instance.post.return_value = mock_response

        with patch("Atlas.key_manager.KeyManager.get_best_key", return_value="dummy_key"):
            with patch("Atlas.memory.buffer.MessageBuffer.get_llm_messages", return_value=[]):
                await Synthesizer.synthesize(
                    [{"model": "x", "output": "y"}], "test", current_topic=None
                )

        system_prompt = mock_instance.post.call_args.kwargs["json"]["messages"][0]["content"]
        assert "[KONU DEĞİŞİMİ]" not in system_prompt
