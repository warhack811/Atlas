"""
ATLAS Router - Session State Management
Tracks active domain, intent history, and context stability.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class SessionState:
    session_id: str
    active_domain: str = "general"
    domain_confidence: float = 1.0
    intent_history: List[str] = field(default_factory=list)
    last_updated: datetime = field(default_factory=datetime.now)
    metadata: Dict = field(default_factory=dict)
    
    def update_domain(self, domain: str, confidence: float):
        """Update domain with history tracking."""
        self.active_domain = domain
        self.domain_confidence = confidence
        self.intent_history.append(domain)
        if len(self.intent_history) > 10:
            self.intent_history.pop(0)
        self.last_updated = datetime.now()

class StateManager:
    _states: Dict[str, SessionState] = {}
    
    @classmethod
    def get_state(cls, session_id: str) -> SessionState:
        if session_id not in cls._states:
            cls._states[session_id] = SessionState(session_id=session_id)
        return cls._states[session_id]
    
    @classmethod
    def clear_state(cls, session_id: str):
        if session_id in cls._states:
            del cls._states[session_id]

state_manager = StateManager()
