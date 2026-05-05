from abc import ABC, abstractmethod
from backend.ws_manager import manager

class BaseAgent(ABC):
    name: str = "base"

    async def emit(self, case_id: str, status: str, content: str = "", extra: dict = None):
        event = {"agent": self.name, "status": status, "content": content}
        if extra:
            event.update(extra)
        await manager.broadcast(case_id, event)

    @abstractmethod
    async def run(self, case_id: str, input_data):
        pass
