from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import asyncio
import json

from backend.ws_manager import manager
from backend.schemas.agents import (
    TileTriageInput,
    HistopathologistInput,
    CrossSlideInput,
    LiteratureHunterInput,
    ChiefInput,
)
from backend.agents.tile_triage import TileTriageAgent
from backend.agents.histopathologist_a import HistopathologistAAgent
from backend.agents.histopathologist_b import HistopathologistBAgent
from backend.agents.cross_slide import CrossSlideAgent
from backend.agents.literature_hunter import LiteratureHunterAgent
from backend.agents.chief import ChiefAgent

app = FastAPI(title="PathMind API", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class AnalyzeRequest(BaseModel):
    case_id: str
    patient_id: str
    slide_paths: list[str]
    clinical_data: Optional[dict] = None


@app.get("/health")
def health():
    return {"ok": True, "version": "0.2.0"}


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
            {"agent": "pipeline", "status": "started", "content": f"{len(req.slide_paths)} slides — dual-read pipeline"},
        )

        # 1. Tile Triage (parallel per slide)
        triage_results = await asyncio.gather(*[
            TileTriageAgent().run(case_id, TileTriageInput(slide_path=p, slide_index=i))
            for i, p in enumerate(req.slide_paths)
        ])

        # 2+3. Histo-A (Qwen72B) + Histo-B (Meditron70B) — parallel for every slide
        histo_inputs = [
            HistopathologistInput(
                slide_index=t.slide_index,
                slide_path=req.slide_paths[t.slide_index],
                regions_of_interest=t.regions_of_interest,
            )
            for t in triage_results
        ]

        results_a, results_b = await asyncio.gather(
            asyncio.gather(*[HistopathologistAAgent().run(case_id, inp) for inp in histo_inputs]),
            asyncio.gather(*[HistopathologistBAgent().run(case_id, inp) for inp in histo_inputs]),
        )

        # 4. Cross-Slide Aggregator (consumes both reads, identifies disagreements)
        cross = await CrossSlideAgent().run(
            case_id,
            CrossSlideInput(
                slides_a=list(results_a),
                slides_b=list(results_b),
                patient_id=req.patient_id,
            ),
        )

        # 5. Literature Hunter
        hypothesis = cross.dominant_pattern or cross.synthesis_a or "indeterminate pathology"
        lit = await LiteratureHunterAgent().run(
            case_id,
            LiteratureHunterInput(
                hypothesis=hypothesis,
                keywords=[cross.dominant_pattern] if cross.dominant_pattern else [],
            ),
        )

        # 6. Chief — debate + arbitration + CAP report
        report = await ChiefAgent().run(
            case_id,
            ChiefInput(
                patient_id=req.patient_id,
                cross_slide=cross,
                literature=lit,
                clinical_data=req.clinical_data or {},
            ),
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
