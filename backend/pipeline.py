import asyncio
from schemas.agents import (CaseInput, TileTriageInput, HistopathologistInput, CrossSlideInput,
    LiteratureHunterInput, DifferentialDxInput, QualityControlInput, ReportWriterInput)
from schemas.events import AgentEvent
from agents.tile_triage import TileTriageAgent
from agents.histopathologist import HistopathologistAgent
from agents.cross_slide import CrossSlideAgent
from agents.literature_hunter import LiteratureHunterAgent
from agents.differential_dx import DifferentialDxAgent
from agents.quality_control import QualityControlAgent
from agents.report_writer import ReportWriterAgent
from ws_manager import WSManager

async def run_pipeline(case_id: str, case: CaseInput, ws: WSManager):
    try:
        slides = case.slides or [type('S',(),{'path':f'demo/slide_{i:02d}.svs','slide_idx':i})() for i in range(4)]
        triage_agent = TileTriageAgent(ws, case_id)
        triage_results = []
        for slide in slides:
            r = await triage_agent.run(TileTriageInput(slide_path=slide.path, slide_idx=slide.slide_idx))
            triage_results.append(r)
        histo_results = await asyncio.gather(*[
            HistopathologistAgent(ws, case_id).run(HistopathologistInput(
                slide_idx=tr.slide_idx, roi_tiles=tr.roi_tiles, clinical_context=case.clinical_context))
            for tr in triage_results])
        cross = await CrossSlideAgent(ws, case_id).run(
            CrossSlideInput(histopath_outputs=list(histo_results), patient_id=case.patient_id))
        lit = await LiteratureHunterAgent(ws, case_id).run(
            LiteratureHunterInput(query=cross.dominant_pattern, dominant_pattern=cross.dominant_pattern))
        diff = await DifferentialDxAgent(ws, case_id).run(
            DifferentialDxInput(synthesis=cross.synthesis, literature_summary=lit.summary, clinical_context=case.clinical_context))
        qc = await QualityControlAgent(ws, case_id).run(
            QualityControlInput(differential=diff, cross_slide=cross, histopath_outputs=list(histo_results)))
        report = await ReportWriterAgent(ws, case_id).run(
            ReportWriterInput(patient_id=case.patient_id, differential=diff, qc=qc,
                              cross_slide=cross, literature=lit, histopath_outputs=list(histo_results)))
        await ws.emit(case_id, AgentEvent(type='pipeline_complete', agent='pipeline', status='complete',
            content=f'Pipeline OK. Dx: {report.final_diagnosis}', confidence=report.confidence).model_dump())
    except Exception as e:
        await ws.emit(case_id, AgentEvent(type='agent_error', agent='pipeline', status='error',
            content=f'Erreur: {str(e)}').model_dump())
        raise
