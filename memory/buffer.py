"""
ATLAS Yönlendirici - Mesaj Tamponu (Message Buffer)
--------------------------------------------------
Bu bileşen, aktif oturumlardaki mesaj geçmişini yönetir. Kullanıcı ve asistan
arasındaki diyaloğu geçici olarak saklar ve LLM'lere uygun formatta sunar.

Temel Sorumluluklar:
1. Mesaj Saklama: Oturum bazlı (session-based) mesaj listeleri tutma.
2. Format Dönüştürme: Kayıtlı mesajları LLM API'lerinin (OpenAI/Gemini) beklediği formata sokma.
3. Kapasite Yönetimi: Bellek tüketimini kontrol etmek için oturum başına mesaj sınırı uygulama.
4. Gelişime Açıklık: Şu an bellek içi (in-memory) çalışsa da Redis veya veritabanı 
   entegrasyonu için gerekli arayüzleri (Protocol) sağlar.
"""

from datetime import datetime
from typing import Optional, Protocol
from dataclasses import dataclass, field


@dataclass
class Message:
    """Sistemdeki tek bir mesaj birimini temsil eden veri sınıfı."""
    role: str  # "user" (kullanıcı) veya "assistant" (asistan)
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Mesajı tüm alanlarıyla birlikte sözlük yapısına dönüştürür."""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }
    
    def to_llm_format(self) -> dict:
        """Mesajı LLM API'lerinin beklediği (role, content) sözlük yapısına çevirir."""
        return {"role": self.role, "content": self.content}


class MessageStore(Protocol):
    """Mesaj depolama arayüzü (Arayüz/Interface). Redis veya SQL sürücüleri buna göre yazılabilir."""
    
    def get_messages(self, session_id: str, limit: int = 10) -> list[Message]: ...
    def add_message(self, session_id: str, message: Message) -> None: ...
    def clear(self, session_id: str) -> None: ...


class InMemoryMessageStore:
    """Bellek içi (RAM) mesaj depolama uygulaması."""
    
    def __init__(self, max_messages_per_session: int = 50):
        self._messages: dict[str, list[Message]] = {}
        self._max = max_messages_per_session
    
    def get_messages(self, session_id: str, limit: int = 10) -> list[Message]:
        """Son N mesajı getir."""
        messages = self._messages.get(session_id, [])
        return messages[-limit:] if limit else messages
    
    def add_message(self, session_id: str, message: Message) -> None:
        """Mesaj ekle."""
        if session_id not in self._messages:
            self._messages[session_id] = []
        
        self._messages[session_id].append(message)
        
        # Max limit kontrolü
        if len(self._messages[session_id]) > self._max:
            self._messages[session_id] = self._messages[session_id][-self._max:]
    
    def clear(self, session_id: str) -> None:
        """Session mesajlarını temizle."""
        self._messages.pop(session_id, None)
    
    def get_session_count(self) -> int:
        """Debug için session sayısı."""
        return len(self._messages)
    
    def get_message_count(self, session_id: str) -> int:
        """Debug için mesaj sayısı."""
        return len(self._messages.get(session_id, []))


# Global message store
_store: MessageStore = InMemoryMessageStore()


class MessageBuffer:
    """Mesaj tamponu yönetimi - Dış katmanlar bu sınıfı kullanır."""
    
    @staticmethod
    def get_history(session_id: str, limit: int = 10) -> list[Message]:
        """Mesaj geçmişini getir."""
        return _store.get_messages(session_id, limit)
    
    @staticmethod
    def get_llm_messages(session_id: str, limit: int = 5) -> list[dict]:
        """LLM formatında mesaj listesi."""
        messages = _store.get_messages(session_id, limit)
        return [m.to_llm_format() for m in messages]
    
    @staticmethod
    def add_user_message(session_id: str, content: str, **metadata) -> Message:
        """Kullanıcı mesajı ekle."""
        msg = Message(role="user", content=content, metadata=metadata)
        _store.add_message(session_id, msg)
        return msg
    
    @staticmethod
    def add_assistant_message(session_id: str, content: str, **metadata) -> Message:
        """Asistan mesajı ekle."""
        msg = Message(role="assistant", content=content, metadata=metadata)
        _store.add_message(session_id, msg)
        return msg
    
    @staticmethod
    def clear(session_id: str) -> None:
        """Mesaj geçmişini temizle."""
        _store.clear(session_id)


# Future: Redis implementation
# class RedisMessageStore:
#     def __init__(self, redis_url: str, ttl_seconds: int = 14400):
#         self.redis = redis.from_url(redis_url)
#         self.ttl = ttl_seconds
#     
#     def get_messages(self, session_id: str, limit: int = 10) -> list[Message]:
#         key = f"session:{session_id}:messages"
#         raw = self.redis.lrange(key, -limit, -1)
#         return [Message(**json.loads(m)) for m in raw]
#     ...
