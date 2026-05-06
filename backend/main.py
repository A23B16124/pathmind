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
from backend.utils import report_cache

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


_SLIDES_ROOTS = [
    Path("/root/pathmind/data/slides"),
    Path("/home/ubuntu/pathmind/data/slides"),
    Path("/data/slides"),
]


def _find_wsi_for_slide_id(slide_id: str) -> Optional[Path]:
    """Resolve a slide_id to a real .svs file on disk.

    Tries (in order):
    1. Exact filename match `{slide_id}.svs` under any slides root (recursive)
    2. Substring match — a stem that contains the slide_id (or vice versa)
    3. Deterministic hash-based fallback to a local test slide so the same
       slide_id always renders the same WSI (avoids flicker on re-fetch).
    """
    for root in _SLIDES_ROOTS:
        if not root.exists():
            continue
        # Exact match
        for cand in root.rglob(f"{slide_id}.svs"):
            return cand
        # Substring match (slide_id in stem or stem in slide_id)
        for cand in root.rglob("*.svs"):
            stem = cand.stem
            if slide_id in stem or stem in slide_id:
                return cand
            # TCGA: match on the patient ID prefix (first 3 dash-separated segments)
            slide_prefix = "-".join(slide_id.split("-")[:3])
            if slide_prefix and slide_prefix in stem:
                return cand

    # Deterministic fallback — pick a real local SVS based on slide_id hash
    pool: list[Path] = []
    for root in _SLIDES_ROOTS:
        if root.exists():
            pool.extend(sorted(root.rglob("*.svs")))
    if not pool:
        return None
    digest = hashlib.md5(slide_id.encode("utf-8")).digest()
    return pool[digest[0] % len(pool)]


@app.get("/api/slide/{slide_id}/thumbnail")
async def slide_thumbnail(slide_id: str, size: int = 1024):
    """Real WSI thumbnail via OpenSlide, cached on disk.

    Resolves slide_id → local .svs file (with TCGA-aware fuzzy matching),
    then extracts a low-res thumbnail with OpenSlide. Falls back to a
    synthetic H&E-textured placeholder if no WSI is available.
    """
    from backend.utils.thumbnail_cache import thumbnail_bytes

    size = max(64, min(2048, int(size)))
    wsi_path = await asyncio.to_thread(_find_wsi_for_slide_id, slide_id)
    data = await asyncio.to_thread(thumbnail_bytes, slide_id, wsi_path, size)
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


@app.get("/api/case/{case_id}/report")
async def get_cached_report(case_id: str):
    """Return the cached pipeline report for case_id, or 404."""
    payload = report_cache.load(case_id)
    if payload is None:
        return Response(
            content=json.dumps({"detail": "report not cached"}),
            status_code=404,
            media_type="application/json",
        )
    return payload


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

            report, literature, warnings, extras = await run_pipeline(
                case_id=case_id,
                patient_id=req.patient_id,
                slide_paths=req.slide_paths,
                clinical_data=req.clinical_data,
            )

            kf = literature.key_findings or ""
            if kf.strip().lower().startswith("[llm"):
                kf = ""

            report_dict = {
                "diagnosis": report.diagnosis,
                "biomarkers": report.biomarkers,
                "debate_summary": report.debate_summary,
                "confidence": report.confidence,
                "cap_report": report.cap_report,
                "report_html": report.report_html,
                "debate_rounds": [d.model_dump() for d in report.debate_rounds],
                "literature": {
                    "key_findings": kf,
                    "similar_cases": literature.similar_cases,
                    "used_papers":      [p.model_dump() for p in literature.used_papers],
                    "suggested_papers": [p.model_dump() for p in literature.suggested_papers],
                },
                "warnings": warnings,
                "histo_a_results": extras["histo_a_results"],
                "histo_b_results": extras["histo_b_results"],
                "cross_slide":     extras["cross_slide"],
                "triage_results":  extras["triage_results"],
                "clinical_data":   extras["clinical_data"],
                "slide_paths":     extras["slide_paths"],
                "patient_id":      req.patient_id,
                "case_id":         case_id,
            }

            # Snapshot the report to disk so the next demo run for this
            # case_id can short-circuit the 5–10 min pipeline and serve via
            # /api/case/{case_id}/report (or future replay).
            try:
                report_cache.save(case_id, report_dict)
            except Exception:
                pass

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
