from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import asyncio

from backend.ws_manager import manager
from backend.schemas.agents import (
    TileTriageInput, HistopathologistInput, CrossSlideInput,
    LiteratureHunterInput, DifferentialDxInput, QualityControlInput, ReportWriterInput,
)
from backend.agents.tile_triage import TileTriageAgent
from backend.agents.histopathologist import HistopathologistAgent
from backend.agents.cross_slide import CrossSlideAgent
from backend.agents.literature_hunter import LiteratureHunterAgent
from backend.agents.differential_dx import DifferentialDxAgent
from backend.agents.quality_control import QualityControlAgent
from backend.agents.report_writer import ReportWriterAgent

app = FastAPI(title="PathMind API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class AnalyzeRequest(BaseModel):
    case_id: str
    patient_id: str
    slide_paths: list[str]
    clinical_data: Optional[dict] = None

@app.get("/health")
def health():
    return {"ok": True, "version": "0.1.0"}

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
    await manager.broadcast(case_id, {"agent": "pipeline", "status": "started", "content": f"{len(req.slide_paths)} lames"})

    triage_results = await asyncio.gather(*[
        TileTriageAgent().run(case_id, TileTriageInput(slide_path=p, slide_index=i))
        for i, p in enumerate(req.slide_paths)
    ])

    histo_results = await asyncio.gather(*[
        HistopathologistAgent().run(case_id, HistopathologistInput(
            slide_index=t.slide_index,
            slide_path=req.slide_paths[t.slide_index],
            regions_of_interest=t.regions_of_interest,
        ))
        for t in triage_results
    ])

    cross = await CrossSlideAgent().run(case_id, CrossSlideInput(slides=list(histo_results), patient_id=req.patient_id))
    lit = await LiteratureHunterAgent().run(case_id, LiteratureHunterInput(hypothesis=cross.synthesis, keywords=[cross.dominant_pattern]))
    dx = await DifferentialDxAgent().run(case_id, DifferentialDxInput(cross_slide=cross, literature=lit, clinical_data=req.clinical_data or {}))
    qc = await QualityControlAgent().run(case_id, QualityControlInput(differential=dx, cross_slide=cross, all_slide_findings=list(histo_results)))
    report = await ReportWriterAgent().run(case_id, ReportWriterInput(patient_id=req.patient_id, differential=dx, qc=qc, literature=lit, cross_slide=cross))

    await manager.broadcast(case_id, {"agent": "pipeline", "status": "complete", "content": report.diagnosis, "confidence": report.confidence})
