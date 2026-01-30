import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from atlas.memory.context import is_reference_needed, build_chat_context_v1
from atlas.memory import MessageBuffer

@pytest.mark.parametrize("text,expected", [
    ("Onu bana ver.", True),
    ("Şunu uzatır mısın?", True),
    ("Orası çok soğuk.", True),
    ("Bunda ne var?", True),
    ("Diğeri nerede?", True),
    ("Ahmet eve geldi.", False),
    ("Hava nasıl bugün?", False),
    ("Bu kitabı okudum.", True),
    ("Öteki ne diyor?", True),
])
def test_is_reference_needed(text, expected):
    """Zamir tespiti (DST) doğrulaması."""
    assert is_reference_needed(text) == expected

@pytest.mark.asyncio
async def test_context_conflict_injection():
    """Çelişki tespit edildiğinde context başına not eklendiğini doğrula."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_active_conflicts.return_value = [
        {"subject": "Ahmet", "predicate": "YAŞIYOR", "value": "İstanbul"}
    ]
    mock_neo4j.get_user_memory_mode.return_value = "STANDARD"
    mock_neo4j.get_recent_turns.return_value = []
    mock_neo4j.query_graph.return_value = [] # Episodic memory bypass
    
    mock_embedder = AsyncMock()
    
    with patch("atlas.memory.context.neo4j_manager", mock_neo4j), \
         patch("atlas.memory.intent.classify_intent_tr", return_value="general"), \
         patch("atlas.memory.context.build_memory_context_v3", return_value=""):
        
        context = await build_chat_context_v1(
            user_id="user123",
            session_id="sess456",
            user_message="Merhaba",
            embedder=mock_embedder
        )
        
        assert "[ÇÖZÜLMESİ GEREKEN DURUM]" in context
        assert "Ahmet YAŞIYOR bilgisi hem 'İstanbul' hem de başka bir değer olarak görünüyor" in context

@pytest.mark.asyncio
async def test_dst_reference_resolution_injection():
    """Zamir kullanıldığında referans notunun eklendiğini doğrula."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_active_conflicts.return_value = []
    mock_neo4j.get_user_memory_mode.return_value = "STANDARD"
    mock_neo4j.get_recent_turns.return_value = []
    mock_neo4j.get_last_active_entity.return_value = "Mami"
    mock_neo4j.query_graph.return_value = [] # Episodic memory bypass
    
    mock_embedder = AsyncMock()
    
    # MessageBuffer'da isim bulma simülasyonu
    with patch("atlas.memory.context.neo4j_manager", mock_neo4j), \
         patch("atlas.memory.intent.classify_intent_tr", return_value="general"), \
         patch("atlas.memory.context.build_memory_context_v3", return_value=""), \
         patch("atlas.memory.buffer.MessageBuffer.get_llm_messages", return_value=[
             {"role": "user", "content": "Mami nerede?"}
         ]):
        
        context = await build_chat_context_v1(
            user_id="user123",
            session_id="sess456",
            user_message="Onu bulamıyorum.", # Zamir içeriyor
            embedder=mock_embedder
        )
        
        assert "[DST_REFERENCE]: Kullanıcı 'Mami' hakkında konuşuyor olabilir." in context
