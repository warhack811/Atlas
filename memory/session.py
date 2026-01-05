"""
ATLAS Yönlendirici - Oturum Yöneticisi (Session Manager)
-------------------------------------------------------
Bu bileşen, kullanıcı etkileşimlerini birbirinden ayıran oturumların (session)
oluşturulmasını, doğrulanmasını ve takibini sağlar.

Temel Sorumluluklar:
1. Oturum Oluşturma: Yeni kullanıcılar için benzersiz Session ID üretimi.
2. Oturum Takibi: Son aktivite zamanını güncelleyerek oturumun canlılığını kontrol etme.
3. Veri Saklama: Oturuma bağlı kullanıcı kimliği ve metadata bilgilerini yönetme.
4. Esnek Altyapı: Bellek içi (In-memory) veya harici (Redis) depolama desteği.
"""

import uuid
from datetime import datetime
from typing import Optional, Protocol
from dataclasses import dataclass, field


@dataclass
class Session:
    """Bir kullanıcı oturumuna ait verileri içeren sınıf."""
    id: str
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    user_id: Optional[str] = None
    metadata: dict = field(default_factory=dict)


class SessionStore(Protocol):
    """Oturum depolama arayüzü. Farklı veritabanı sürücüleri için temel teşkil eder."""
    
    def get(self, session_id: str) -> Optional[Session]: ...
    def set(self, session: Session) -> None: ...
    def delete(self, session_id: str) -> None: ...
    def touch(self, session_id: str) -> None: ...


class InMemorySessionStore:
    """Bellek içi (RAM) oturum depolama uygulaması."""
    
    def __init__(self):
        self._sessions: dict[str, Session] = {}
    
    def get(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)
    
    def set(self, session: Session) -> None:
        self._sessions[session.id] = session
    
    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
    
    def touch(self, session_id: str) -> None:
        """Son aktivite zamanını güncelle."""
        if session_id in self._sessions:
            self._sessions[session_id].last_activity = datetime.now()


# Küresel oturum deposu (MVP-1: bellek içi, MVP-2: Redis)
_store: SessionStore = InMemorySessionStore()


class SessionManager:
    """Oturum yönetimi için ana kontrolcü."""
    
    @staticmethod
    def get_or_create(session_id: Optional[str] = None) -> Session:
        """
        Session al veya oluştur.
        
        Args:
            session_id: Mevcut session ID (cookie/header'dan)
        
        Returns:
            Session object
        """
        if session_id:
            session = _store.get(session_id)
            if session:
                _store.touch(session_id)
                return session
        
        # Yeni session oluştur (Sandbox/Dev için sağlanan ID'yi koru)
        actual_id = session_id if session_id else str(uuid.uuid4())[:8]
        new_session = Session(id=actual_id)
        _store.set(new_session)
        return new_session
    
    @staticmethod
    def get(session_id: str) -> Optional[Session]:
        """Session al."""
        return _store.get(session_id)
    
    @staticmethod
    def delete(session_id: str) -> None:
        """Session sil."""
        _store.delete(session_id)


# Future: Redis implementation
# class RedisSessionStore:
#     def __init__(self, redis_url: str, ttl_seconds: int = 14400):
#         self.redis = redis.from_url(redis_url)
#         self.ttl = ttl_seconds
#     ...
