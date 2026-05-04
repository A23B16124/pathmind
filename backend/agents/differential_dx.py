from backend.agents.base import BaseAgent
from backend.schemas.agents import DifferentialDxInput, DifferentialDxOutput
from backend.llm import chat

class DifferentialDxAgent(BaseAgent):
    name = "differential_diagnostician"

    async def run(self, case_id: str, input_data: DifferentialDxInput) -> DifferentialDxOutput:
        await self.emit(case_id, "running", "Etablissement diagnostics differentiels")
        result = await chat(
            system="Tu es un diagnosticien expert. Propose 3-5 diagnostics differentiels ranked par probabilite. Format: primary_diagnosis (str), differentials (list: name, probability, rationale), confidence (float).",
            messages=[{"role": "user", "content": f"Synthese: {input_data.cross_slide.synthesis}\nLitterature: {input_data.literature.key_findings}"}],
        )
        await self.emit(case_id, "done", result)
        return DifferentialDxOutput(primary_diagnosis=result, confidence=0.91)
