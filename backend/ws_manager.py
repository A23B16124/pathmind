"""
WebSocket connection manager with per-case event buffer (Task 4).

Events are buffered in memory so a reconnecting client can replay missed
events. Buffer is capped at MAX_BUFFER_PER_CASE to bound memory.
Buffer is cleared when the pipeline completes (status == "complete"/"error").
"""

from __future__ import annotations

import json
from collections import deque
from typing import Dict, Deque, List

from fastapi import WebSocket

MAX_BUFFER_PER_CASE = 500  # max events to keep per case_id


class ConnectionManager:
    def __init__(self):
        self.active: Dict[str, List[WebSocket]] = {}
        self._buffers: Dict[str, Deque[dict]] = {}

    async def connect(self, case_id: str, ws: WebSocket):
        await ws.accept()
        self.active.setdefault(case_id, []).append(ws)
        # Replay buffered events so late-joining clients catch up
        for event in self._buffers.get(case_id, []):
            try:
                await ws.send_text(json.dumps(event))
            except Exception:
                break

    def disconnect(self, case_id: str, ws: WebSocket):
        if case_id in self.active:
            try:
                self.active[case_id].remove(ws)
            except ValueError:
                pass

    async def broadcast(self, case_id: str, event: dict):
        # Buffer the event
        buf = self._buffers.setdefault(case_id, deque(maxlen=MAX_BUFFER_PER_CASE))
        buf.append(event)

        # Clear buffer when pipeline finishes
        status = event.get("status", "")
        if status in ("complete", "error") and event.get("agent") == "pipeline":
            self._buffers.pop(case_id, None)

        # Broadcast to connected clients
        dead: list[WebSocket] = []
        for ws in self.active.get(case_id, []):
            try:
                await ws.send_text(json.dumps(event))
            except Exception:
                dead.append(ws)

        for ws in dead:
            self.disconnect(case_id, ws)


manager = ConnectionManager()
