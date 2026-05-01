import asyncio
import json
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator

app = FastAPI()
_queues: dict[str, asyncio.Queue] = {}


def get_queue(case_id: str) -> asyncio.Queue:
    if case_id not in _queues:
        _queues[case_id] = asyncio.Queue()
    return _queues[case_id]


async def emit(case_id: str, event: str, data: dict) -> None:
    await get_queue(case_id).put({"event": event, "data": data})


async def _sse_generator(case_id: str) -> AsyncGenerator[str, None]:
    q = get_queue(case_id)
    while True:
        msg = await q.get()
        yield f"event: {msg['event']}\ndata: {json.dumps(msg['data'])}\n\n"
        if msg["event"] == "report_ready":
            break


@app.get("/stream/{case_id}")
async def stream(case_id: str):
    return StreamingResponse(
        _sse_generator(case_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
