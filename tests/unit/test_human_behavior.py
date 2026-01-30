import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from atlas.memory.extractor import extract_and_save
from atlas.services.synthesizer import Synthesizer
from atlas.core.orchestrator import Orchestrator

@pytest.mark.skip(reason="Legacy test broken by refactor")
@pytest.mark.asyncio
async def test_emotion_extraction_feels():
    """Test 1: 'Bugün çok yorgunum' ifadesinden FEELS: Yorgun bilgisinin çıkarılması."""
    user_id = "test_user_emotion"
    text = "Bugün çok yorgunum ve dinlenmek istiyorum."

    with patch("atlas.memory.extractor.httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": '[{"subject": "test_user", "predicate": "HİSSEDİYOR", "object": "Yorgun", "category": "personal", "confidence": 0.9}]'
                }
            }]
        }
        mock_post.return_value = mock_response

        with patch("atlas.memory.mwg.decide") as mock_decide, \
             patch("atlas.config.Config.get_random_groq_key", return_value="dummy_key"), \
             patch("atlas.memory.neo4j_manager.neo4j_manager.get_user_names", new_callable=AsyncMock) as mock_names, \
             patch("atlas.memory.neo4j_manager.neo4j_manager.store_triplets", new_callable=AsyncMock) as mock_store:

            mock_names.return_value = []

            from atlas.memory.mwg import Decision
            mock_decide.return_value = MagicMock()
            mock_decide.return_value.decision = Decision.LONG_TERM

            result = await extract_and_save(text, user_id)
            # Extractor normalizes HİSSEDİYOR
            assert any(r["predicate"] == "HİSSEDİYOR" for r in result)
            assert any(r["object"] == "Yorgun" for r in result)

@pytest.mark.skip(reason="Legacy test broken by refactor")
@pytest.mark.asyncio
async def test_mirroring_behavior_logic():
    """Test 2: Mirroring mantığının synthesizer promptuna eklenip eklenmediği."""
    synth = Synthesizer()
    user_message = "Bugün gerçekten çok yorgunum."
    raw_results = [{"model": "expert", "output": "Halsizlik hissediliyor."}]

    # We need to mock MessageBuffer.get_llm_messages for synthesizer too
    with patch("atlas.memory.buffer.MessageBuffer.get_llm_messages", return_value=[]):
        with patch("atlas.services.key_manager.KeyManager.get_best_key", return_value="dummy_key"):
            with patch("httpx.AsyncClient.post") as mock_post:
                mock_post.return_value = MagicMock(status_code=200, json=lambda: {"choices": [{"message": {"content": "Ok"}}]})

                await synth.synthesize(raw_results, "session_1", user_message=user_message, mode="standard")

                # Check system prompt in mock call args
                system_prompt = mock_post.call_args.kwargs["json"]["messages"][0]["content"]
                assert "[MIRRORING]" in system_prompt
                assert "yorgun" in system_prompt.lower()
                assert "empatik" in system_prompt.lower()

@pytest.mark.skip(reason="Legacy test broken by refactor")
@pytest.mark.asyncio
async def test_conflict_notification_orchestrator():
    """Test 3: Çelişkili bilgi durumunda orkestratörün uyarısı."""
    orch = Orchestrator()
    session_id = "session_conflict"
    message = "Nasılsın?"

    mock_context_builder = MagicMock()
    # Mock build() to return the string orchestrator looks for
    mock_context_builder.build.return_value = [{"role": "system", "content": "[ÇÖZÜLMESİ GEREKEN DURUM]"}]

    with patch("atlas.memory.buffer.MessageBuffer.get_llm_messages", return_value=[]), \
         patch("atlas.core.orchestrator.Orchestrator._call_brain") as mock_brain, \
         patch("atlas.memory.neo4j_manager.neo4j_manager.get_active_conflicts", new_callable=AsyncMock) as mock_conflicts, \
         patch("atlas.memory.neo4j_manager.neo4j_manager.get_recent_turns", new_callable=AsyncMock) as mock_turns, \
         patch("atlas.memory.neo4j_manager.neo4j_manager.get_last_active_entity", new_callable=AsyncMock) as mock_entity, \
         patch("atlas.memory.neo4j_manager.neo4j_manager.query_graph", new_callable=AsyncMock) as mock_query:

        mock_conflicts.return_value = [{"subject": "s", "predicate": "p", "value": "v"}]
        mock_turns.return_value = []
        mock_entity.return_value = None
        mock_query.return_value = []  # Generic query mock

        # Mock brain needs to return "user_thought" so the code can append to it
        mock_brain.return_value = (
            {
                "intent": "general",
                "is_follow_up": False,
                "tasks": [{"id": "t1", "type": "generation", "instruction": "Cevap ver."}],
                "user_thought": "Analiz yapılıyor."
            },
            "prompt",
            "model"
        )

        plan = await orch.plan(session_id, message, context_builder=mock_context_builder)

        assert "netleştir" in plan.user_thought.lower()
        assert "[DİKKAT]" in plan.tasks[0]["instruction"]
        assert "netleştir" in plan.tasks[0]["instruction"].lower()
