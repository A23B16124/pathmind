from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Any, Optional
import asyncio
import colorsys
import hashlib
import json
import os
import random
import time
from pathlib import Path

import httpx
from PIL import Image

from backend.ws_manager import manager
from backend.graph import run_pipeline
from backend.report_export import render_pdf, render_docx
from backend.api.slides import router as slides_router

app = FastAPI(title="PathMind API", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(slides_router)

_STARTUP_TIME = time.time()

# Cap how many cases run concurrently. Each case fans out across many agents
# and the underlying LLM semaphore already throttles per-call concurrency, but
# this guards against the wider scheduler drowning under burst load.
_CASE_MAX_CONCURRENCY = int(os.getenv("CASE_MAX_CONCURRENCY", "3"))
_CASE_SEMAPHORE = asyncio.Semaphore(_CASE_MAX_CONCURRENCY)
_CASE_INFLIGHT: dict[str, asyncio.Task] = {}


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
    """Submit a case. Idempotent on case_id while a previous run is in-flight."""
    existing = _CASE_INFLIGHT.get(req.case_id)
    if existing and not existing.done():
        return {"case_id": req.case_id, "status": "already_running"}

    task = asyncio.create_task(_run_pipeline(req))
    _CASE_INFLIGHT[req.case_id] = task
    task.add_done_callback(lambda _t: _CASE_INFLIGHT.pop(req.case_id, None))
    return {
        "case_id": req.case_id,
        "status": "started",
        "queue_size": len([t for t in _CASE_INFLIGHT.values() if not t.done()]),
    }


class ReportExportRequest(BaseModel):
    report: dict
    patient_label: str = ""
    filename: str = "rapport"


def _safe_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)[:80] or "rapport"


@app.post("/api/report/pdf")
async def export_report_pdf(req: ReportExportRequest):
    """Render a CAP-style PDF for the given report payload."""
    pdf_bytes = await asyncio.to_thread(render_pdf, req.report, req.patient_label)
    fname = _safe_filename(req.filename) + ".pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.post("/api/report/docx")
async def export_report_docx(req: ReportExportRequest):
    """Render a CAP-style DOCX for the given report payload."""
    docx_bytes = await asyncio.to_thread(render_docx, req.report, req.patient_label)
    fname = _safe_filename(req.filename) + ".docx"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


_THUMB_CACHE_DIR = Path("/tmp/pathmind_thumbs")
_THUMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Mock ROI overlays — kept aligned with the frontend FALLBACK_OVERLAYS
# so 2D and 3D demo views show the same regions.
_MOCK_OVERLAYS = [
    {"x": 0.18, "y": 0.22, "w": 0.16, "h": 0.12, "tissue": 0.78, "label": "ROI 1"},
    {"x": 0.55, "y": 0.18, "w": 0.10, "h": 0.09, "tissue": 0.71, "label": "ROI 2"},
    {"x": 0.30, "y": 0.55, "w": 0.14, "h": 0.11, "tissue": 0.66, "label": "ROI 3"},
    {"x": 0.62, "y": 0.60, "w": 0.12, "h": 0.10, "tissue": 0.59, "label": "ROI 4"},
]

_DEMO_DUBOIS_SLIDE_NAMES = [
    "Dubois-tete-pancreas-01.svs",
    "Dubois-tete-pancreas-02.svs",
    "Dubois-tete-pancreas-03.svs",
]


def _generate_thumbnail(slide_id: str, size: int) -> bytes:
    """Deterministic tissue-coloured JPEG keyed on slide_id."""
    digest = hashlib.md5(slide_id.encode("utf-8")).digest()
    hue = digest[0] / 255.0  # 0..1
    sat = 0.30 + (digest[1] / 255.0) * 0.20  # 0.30..0.50, brownish
    light = 0.55 + (digest[2] / 255.0) * 0.20  # 0.55..0.75
    r, g, b = colorsys.hls_to_rgb(hue, light, sat)
    base = (int(r * 255), int(g * 255), int(b * 255))

    img = Image.new("RGB", (size, size), base)
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    pixels = img.load()
    for y in range(size):
        for x in range(0, size, 4):  # sparse noise — fast, still grainy
            n = rng.randint(-18, 18)
            px = pixels[x, y]
            pixels[x, y] = (
                max(0, min(255, px[0] + n)),
                max(0, min(255, px[1] + n)),
                max(0, min(255, px[2] + n)),
            )

    from io import BytesIO
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=82)
    return buf.getvalue()


@app.get("/api/slide/{slide_id}/thumbnail")
async def slide_thumbnail(slide_id: str, size: int = 1024):
    """Placeholder tissue-tinted thumbnail. Cached on disk under /tmp/pathmind_thumbs/."""
    safe_id = "".join(c if c.isalnum() or c in "-_." else "_" for c in slide_id)[:120]
    size = max(64, min(2048, int(size)))
    cache_path = _THUMB_CACHE_DIR / f"{safe_id}-{size}.jpg"

    if cache_path.exists():
        data = await asyncio.to_thread(cache_path.read_bytes)
    else:
        data = await asyncio.to_thread(_generate_thumbnail, slide_id, size)
        await asyncio.to_thread(cache_path.write_bytes, data)

    return Response(content=data, media_type="image/jpeg")


@app.get("/api/case/{case_id}/slides")
async def case_slides(case_id: str):
    """Mock slide list for the Dubois demo case (3 slides + ROI overlays)."""
    slides = []
    for i, name in enumerate(_DEMO_DUBOIS_SLIDE_NAMES):
        slide_id = f"{case_id}-{i}"
        slides.append({
            "id": slide_id,
            "index": i,
            "name": name,
            "thumbnail_url": f"/api/slide/{slide_id}/thumbnail",
            "rois": _MOCK_OVERLAYS[: 3 + (i % 2)],  # 3 or 4 ROIs per slide
        })
    return {"case_id": case_id, "slides": slides}


@app.get("/api/queue")
async def queue_status():
    active = [cid for cid, t in _CASE_INFLIGHT.items() if not t.done()]
    return {
        "active_cases": active,
        "active_count": len(active),
        "max_concurrent": _CASE_MAX_CONCURRENCY,
    }


async def _run_pipeline(req: AnalyzeRequest):
    """Run the LangGraph pipeline for one case under the case-level semaphore."""
    case_id = req.case_id
    async with _CASE_SEMAPHORE:
        try:
            await manager.broadcast(
                case_id,
                {"agent": "pipeline", "status": "started",
                 "content": f"{len(req.slide_paths)} slides — LangGraph dual-read pipeline"},
            )

            report, literature, warnings = await run_pipeline(
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
                "literature": {
                    "key_findings": literature.key_findings,
                    "similar_cases": literature.similar_cases,
                    "used_papers":      [p.model_dump() for p in literature.used_papers],
                    "suggested_papers": [p.model_dump() for p in literature.suggested_papers],
                },
                "warnings": warnings,
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
