from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import asyncio
import json
import os
import time

import httpx

from backend.ws_manager import manager
from backend.graph import run_pipeline

app = FastAPI(title="PathMind API", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_STARTUP_TIME = time.time()


class AnalyzeRequest(BaseModel):
    case_id: str
    patient_id: str
    slide_paths: list[str]
    clinical_data: Optional[dict] = None


async def _probe(url: str, timeout: float = 1.0) -> bool:
    """1-second probe of an OpenAI-compatible /models endpoint."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.get(url.rstrip("/") + "/models")
            return r.status_code == 200
    except Exception:
        return False


def _qdrant_status() -> dict:
    """Probe Qdrant via the existing rag.search client. Never raises."""
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    collection = os.getenv("PATHMIND_COLLECTION", "pathmind_literature")
    try:
        from backend.rag.search import _client
        client = _client()
        info = client.get_collection(collection)
        return {
            "url": qdrant_url,
            "reachable": True,
            "literature_chunks": info.points_count or 0,
        }
    except Exception:
        return {
            "url": qdrant_url,
            "reachable": False,
            "literature_chunks": 0,
        }


@app.get("/health")
async def health():
    from backend.llm import LLM_BACKEND, VLLM_BASE_URL_MAP

    qwen_url = VLLM_BASE_URL_MAP["qwen72b"]
    meditron_url = VLLM_BASE_URL_MAP["meditron70b"]

    qwen_ok, meditron_ok = await asyncio.gather(
        _probe(qwen_url),
        _probe(meditron_url),
    )
    qdrant = await asyncio.to_thread(_qdrant_status)

    return {
        "ok": True,
        "version": "0.2.0",
        "llm_backend": LLM_BACKEND,
        "vllm_models": {
            "qwen72b":     {"url": qwen_url,     "reachable": qwen_ok},
            "meditron70b": {"url": meditron_url, "reachable": meditron_ok},
        },
        "qdrant": qdrant,
        "agents": [
            "tile-triage",
            "histopathologist-a",
            "histopathologist-b",
            "cross-slide-aggregator",
            "literature-hunter",
            "chief",
        ],
        "uptime_seconds": int(time.time() - _STARTUP_TIME),
    }


@app.websocket("/ws/{case_id}")
async def websocket_endpoint(websocket: WebSocket, case_id: str):
    await manager.connect(case_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(case_id, websocket)


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    asyncio.create_task(_run_pipeline(req))
    return {"case_id": req.case_id, "status": "started"}


async def _run_pipeline(req: AnalyzeRequest):
    case_id = req.case_id
    try:
        await manager.broadcast(
            case_id,
            {"agent": "pipeline", "status": "started", "content": f"{len(req.slide_paths)} slides — LangGraph dual-read pipeline"},
        )

        report = await run_pipeline(
            case_id=case_id,
            patient_id=req.patient_id,
            slide_paths=req.slide_paths,
            clinical_data=req.clinical_data,
        )

        report_dict = {
            "diagnosis": report.diagnosis,
            "biomarkers": report.biomarkers,
            "debate_summary": report.debate_summary,
            "confidence": report.confidence,
            "cap_report": report.cap_report,
            "report_html": report.report_html,
        }

        # content = JSON-stringified report so frontend ws.ts parser works.
        # report = same dict for forward-compat consumers.
        await manager.broadcast(
            case_id,
            {
                "agent": "pipeline",
                "status": "complete",
                "content": json.dumps(report_dict),
                "confidence": report.confidence,
                "report": report_dict,
            },
        )

    except Exception as e:
        await manager.broadcast(
            case_id,
            {"agent": "pipeline", "status": "error", "content": f"Pipeline error: {e}"},
        )
        raise
