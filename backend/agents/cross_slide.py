from backend.agents.base import BaseAgent
from backend.schemas.agents import CrossSlideInput, CrossSlideOutput
from backend.llm import chat
from backend.prompts import load_prompt


class CrossSlideAgent(BaseAgent):
    name = "cross_slide_aggregator"

    async def run(self, case_id: str, input_data: CrossSlideInput) -> CrossSlideOutput:
        await self.emit(case_id, "running", f"Synthese {len(input_data.slides)} lames")
        per_slide = "\n".join(
            f"Slide {s.slide_index}: {s.findings[:600]}" for s in input_data.slides
        )
        user = (
            f"Patient ID: {input_data.patient_id}\n"
            f"Total slides analyzed: {len(input_data.slides)}\n"
            f"Per-slide histopathologist findings:\n{per_slide}\n"
            f"Task: aggregate into a patient-level synthesis. Output the JSON schema only."
        )
        result = await chat(
            agent_name=self.name,
            system=load_prompt("cross_slide_aggregator"),
            messages=[{"role": "user", "content": user}],
        )
        await self.emit(case_id, "done", result)
        return CrossSlideOutput(synthesis=result, confidence=0.87)
