import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from Atlas.memory.extractor import extract_and_save
from Atlas.synthesizer import Synthesizer
from Atlas.orchestrator import Orchestrator

@pytest.mark.asyncio
async def test_emotion_extraction_feels():
    """Test 1: 'Bugün çok yorgunum' ifadesinden FEELS: Yorgun bilgisinin çıkarılması."""
    user_id = "test_user_emotion"
    text = "Bugün çok yorgunum ve dinlenmek istiyorum."
    
    with patch("Atlas.memory.extractor.httpx.AsyncClient.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "choices": [{
                "message": {
                    "content": '[{"subject": "test_user", "predicate": "HİSSEDİYOR", "object": "Yorgun", "category": "personal", "confidence": 0.9}]'
                }
            }]
        }
        with patch("Atlas.memory.extractor.decide") as mock_decide:
            from Atlas.memory.mwg import Decision
            mock_decide.return_value = MagicMock()
            mock_decide.return_value.decision = Decision.LONG_TERM
            
            result = await extract_and_save(text, user_id)
            # Extractor normalizes HİSSEDİYOR
            assert any(r["predicate"] == "HİSSEDİYOR" for r in result)
            assert any(r["object"] == "Yorgun" for r in result)

@pytest.mark.asyncio
async def test_mirroring_behavior_logic():
    """Test 2: Mirroring mantığının synthesizer promptuna eklenip eklenmediği."""
    synth = Synthesizer()
    user_message = "Bugün gerçekten çok yorgunum."
    raw_results = [{"model": "expert", "output": "Halsizlik hissediliyor."}]
    
    # We need to mock MessageBuffer.get_llm_messages for synthesizer too
    with patch("Atlas.synthesizer.MessageBuffer.get_llm_messages", return_value=[]):
        _, _, prompt, _ = await synth.synthesize(raw_results, "session_1", user_message=user_message, mode="standard")
        
        assert "[MIRRORING]" in prompt
        assert "yorgun" in prompt.lower()
        assert "empatik" in prompt.lower()

@pytest.mark.asyncio
async def test_conflict_notification_orchestrator():
    """Test 3: Çelişkili bilgi durumunda orkestratörün uyarısı."""
    orch = Orchestrator()
    session_id = "session_conflict"
    message = "Nasılsın?"
    
    mock_context_builder = MagicMock()
    mock_context_builder._neo4j_context = "[GRAF | Skor: 0.9]: Özne HİSSEDİYOR Nesne (status: CONFLICTED)"
    
    with patch("Atlas.orchestrator.MessageBuffer.get_llm_messages", return_value=[]), \
         patch("Atlas.orchestrator.Orchestrator._call_brain") as mock_brain:
        
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
