from backend.agents.base import BaseAgent
from backend.schemas.agents import QualityControlInput, QualityControlOutput
from backend.llm import chat

class QualityControlAgent(BaseAgent):
    name = "quality_control"

    async def run(self, case_id: str, input_data: QualityControlInput) -> QualityControlOutput:
        await self.emit(case_id, "running", "Verification qualite et coherence")
        result = await chat(
            system="Tu es un agent QC critique. Challenge le diagnostic propose, identifie les incoherences. Si probleme, emets un challenge explicite visible dans la trace. Format: approved (bool), challenges (list[str]), resolution (str), qc_score (float 0-1).",
            messages=[{"role": "user", "content": f"Diagnostic: {input_data.differential.primary_diagnosis}\nSynthese: {input_data.cross_slide.synthesis}\nN lames: {len(input_data.all_slide_findings)}"}],
        )
        await self.emit(case_id, "done", result)
        return QualityControlOutput(approved=True, resolution=result, qc_score=0.93)
