from abc import ABC, abstractmethod
from typing import List, Dict, Optional

class ContextStrategy(ABC):
    @abstractmethod
    async def get_context(self, user_id: str, session_id: str, message: str) -> str:
        pass

class TemporalContextStrategy(ContextStrategy):
    async def get_context(self, user_id: str, session_id: str, message: str) -> str:
        # Implementation of temporal context logic
        return ""

class EpisodicContextStrategy(ContextStrategy):
    async def get_context(self, user_id: str, session_id: str, message: str) -> str:
        # Implementation of episodic context logic
        return ""
