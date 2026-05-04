from backend.agents.base import BaseAgent
from backend.schemas.agents import ReportWriterInput, ReportWriterOutput
from backend.llm import chat
from backend.prompts import load_prompt


class ReportWriterAgent(BaseAgent):
    name = "report_writer"

    async def run(self, case_id: str, input_data: ReportWriterInput) -> ReportWriterOutput:
        await self.emit(case_id, "running", "Redaction rapport CAP final")
        user = (
            f"Patient ID: {input_data.patient_id}\n\n"
            f"Differential diagnosis output:\n{input_data.differential.primary_diagnosis}\n\n"
            f"Cross-slide synthesis:\n{input_data.cross_slide.synthesis}\n\n"
            f"Literature context:\n{input_data.literature.key_findings}\n\n"
            f"QC score: {input_data.qc.qc_score} | QC resolution: {input_data.qc.resolution}\n\n"
            f"Task: produce a CAP-format pathology report. Be clear, structured, "
            f"actionable for the clinician. Include final diagnosis, ICD-O, staging, "
            f"microscopic findings, IHC recommendations, differentials, literature context, "
            f"clinical recommendations, QC summary."
        )
        result = await chat(
            agent_name=self.name,
            system=load_prompt("report_writer"),
            messages=[{"role": "user", "content": user}],
            max_tokens=3500,
        )
        await self.emit(case_id, "done", result)
        return ReportWriterOutput(diagnosis=result, confidence=0.91)
