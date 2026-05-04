from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class AgentEvent(BaseModel):
    type: str = 'agent_progress'
    agent: str
    slide_idx: Optional[int] = None
    status: str = 'running'
    content: str = ''
    confidence: Optional[float] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
