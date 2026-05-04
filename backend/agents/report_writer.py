from backend.agents.base import BaseAgent
from backend.schemas.agents import ReportWriterInput, ReportWriterOutput
from backend.llm import chat

class ReportWriterAgent(BaseAgent):
    name = "report_writer"

    async def run(self, case_id: str, input_data: ReportWriterInput) -> ReportWriterOutput:
        await self.emit(case_id, "running", "Redaction rapport CAP final")
        result = await chat(
            system="Tu es un redacteur de rapports pathologiques format CAP. Redige un rapport structure: diagnosis, tumor_type, grade, margins, biomarkers (list), confidence. Clair et actionnable pour un clinicien.",
            messages=[{"role": "user", "content": f"Patient: {input_data.patient_id}\nDiagnostic: {input_data.differential.primary_diagnosis}\nQC: {input_data.qc.qc_score}\nCas similaires: {input_data.literature.similar_cases}"}],
            max_tokens=3000,
        )
        await self.emit(case_id, "done", result)
        return ReportWriterOutput(diagnosis=result, confidence=0.91)
