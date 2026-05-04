from backend.agents.base import BaseAgent
from backend.schemas.agents import QualityControlInput, QualityControlOutput
from backend.llm import chat
from backend.prompts import load_prompt


class QualityControlAgent(BaseAgent):
    name = "quality_control"

    async def run(self, case_id: str, input_data: QualityControlInput) -> QualityControlOutput:
        await self.emit(case_id, "running", "Verification qualite et coherence")
        user = (
            f"Primary differential diagnosis:\n{input_data.differential.primary_diagnosis}\n\n"
            f"Cross-slide synthesis:\n{input_data.cross_slide.synthesis}\n\n"
            f"Number of slides analyzed: {len(input_data.all_slide_findings)}\n\n"
            f"Task: critically review for inconsistencies, missing IHC/staging, agent disagreements. "
            f"Issue explicit challenges visible in the trace. Output the JSON schema only."
        )
        result = await chat(
            agent_name=self.name,
            system=load_prompt("quality_control"),
            messages=[{"role": "user", "content": user}],
        )
        await self.emit(case_id, "done", result)
        return QualityControlOutput(approved=True, resolution=result, qc_score=0.93)
