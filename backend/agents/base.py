from abc import ABC, abstractmethod
from backend.ws_manager import manager


class BaseAgent(ABC):
    name: str = "base"

    # Task 9: singleton per subclass to avoid per-call object churn
    _instances: dict = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._instances = {}

    @classmethod
    def instance(cls):
        if cls not in cls._instances:
            cls._instances[cls] = cls()
        return cls._instances[cls]

    async def emit(self, case_id: str, status: str, content: str = "", extra: dict = None):
        event = {"agent": self.name, "status": status, "content": content}
        if extra:
            event.update(extra)
        await manager.broadcast(case_id, event)

    @abstractmethod
    async def run(self, case_id: str, input_data):
        pass
