from fastapi import WebSocket
from typing import Dict, List
import json

class ConnectionManager:
    def __init__(self):
        self.active: Dict[str, List[WebSocket]] = {}

    async def connect(self, case_id: str, ws: WebSocket):
        await ws.accept()
        self.active.setdefault(case_id, []).append(ws)

    def disconnect(self, case_id: str, ws: WebSocket):
        if case_id in self.active:
            self.active[case_id].remove(ws)

    async def broadcast(self, case_id: str, event: dict):
        for ws in self.active.get(case_id, []):
            try:
                await ws.send_text(json.dumps(event))
            except Exception:
                pass

manager = ConnectionManager()
