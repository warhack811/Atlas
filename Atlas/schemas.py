"""
ATLAS Yönlendirici - Veri Şemaları (Schemas)
--------------------------------------------
Bu modül, sistem içinde dolaşan verilerin yapısal doğruluğunu sağlamak için 
Pydantic modellerini tanımlar.
"""
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field

class TaskSpec(BaseModel):
    """Bir görevin (Generation veya Tool) tanımı."""
    id: str
    type: str = Field(..., description="'generation' veya 'tool'")
    specialist: Optional[str] = None
    instruction: Optional[str] = None
    prompt: Optional[str] = None
    tool_name: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    dependencies: List[str] = Field(default_factory=list)

class OrchestrationPlan(BaseModel):
    """Orchestrator'dan gelen tam plan."""
    intent: str
    detected_topic: Optional[str] = Field(default="SAME", description="Algılanan konuşma konusu")
    rewritten_query: Optional[str] = None
    user_thought: Optional[str] = None
    reasoning: Optional[str] = None
    orchestrator_prompt: Optional[str] = None
    orchestrator_model: Optional[str] = None
    tasks: List[TaskSpec]
