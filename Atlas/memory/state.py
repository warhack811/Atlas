"""
ATLAS Router - Session State Management
Tracks active domain, intent history, and context stability.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta

@dataclass
class SessionState:
    session_id: str
    active_domain: str = "general"
    domain_confidence: float = 1.0
    intent_history: List[str] = field(default_factory=list)
    last_updated: datetime = field(default_factory=datetime.now)
    metadata: Dict = field(default_factory=dict)
    current_topic: str = "Genel"
    topic_history: List[str] = field(default_factory=list)
    _hydrated: bool = False  # FAZ-α: Topic DB kontrolü yapıldı mı?
    
    # FAZ-γ: Identity Cache (Cross-Session Memory Persistence)
    _identity_cache: Dict[str, str] = field(default_factory=dict)  # {"ISIM": "Muhammet", "YASI": "25"}
    _identity_hydrated: bool = False  # Identity DB check flag
    
    def update_domain(self, domain: str, confidence: float):
        """Update domain with history tracking."""
        self.active_domain = domain
        self.domain_confidence = confidence
        self.intent_history.append(domain)
        if len(self.intent_history) > 10:
            self.intent_history.pop(0)
        self.last_updated = datetime.now()

    def update_topic(self, new_topic: str):
        """Update active topic if significantly changed."""
        if not new_topic or new_topic in ["SAME", "CHITCHAT"]:
            return
            
        # Title Case normalization
        new_topic = new_topic.title()
        
        if new_topic != self.current_topic:
            self.topic_history.append(self.current_topic)
            if len(self.topic_history) > 5:
                self.topic_history.pop(0)
            self.current_topic = new_topic
            self.last_updated = datetime.now()
            
            # FAZ-α FIX: Topic değiştiğinde hydration flag'ini resetle
            # Böylece server restart sonrası yeni topic'ten restore yapabilir
            self._hydrated = False

class StateManager:
    _states: Dict[str, SessionState] = {}
    _last_cleanup: datetime = datetime.now()
    
    @classmethod
    def get_state(cls, session_id: str) -> SessionState:
        # Periodic cleanup (her 1 saatte bir) - 1GB RAM Koruması
        if (datetime.now() - cls._last_cleanup).seconds > 3600:
            cls._cleanup_stale_sessions()
            cls._last_cleanup = datetime.now()
        
        if session_id not in cls._states:
            cls._states[session_id] = SessionState(session_id=session_id)
        return cls._states[session_id]
    
    @classmethod
    def _cleanup_stale_sessions(cls):
        """Remove sessions older than 24 hours to prevent memory leaks."""
        try:
            cutoff = datetime.now() - timedelta(hours=24)
            stale_sessions = [
                sid for sid, state in cls._states.items()
                if state.last_updated < cutoff
            ]
            for sid in stale_sessions:
                del cls._states[sid]
            if stale_sessions:
                print(f"[CLEANUP]: {len(stale_sessions)} stale sessions removed from RAM.")
        except Exception as e:
            print(f"[CLEANUP ERROR]: {e}")
    
    @classmethod
    def clear_state(cls, session_id: str):
        if session_id in cls._states:
            del cls._states[session_id]

    @classmethod
    def clear_user_cache(cls, user_id: str):
        """Kullanıcıya ait (eğer session_id user_id'yi içeriyorsa) veya tüm cache'i temizler.
        FAZ-Y: RAM Leak protection & Consistency.
        """
        to_delete = [sid for sid in cls._states.keys() if user_id in sid.lower()]
        for sid in to_delete:
            del cls._states[sid]
        if to_delete:
            print(f"[CACHE]: {len(to_delete)} session states cleared for {user_id}")

state_manager = StateManager()
