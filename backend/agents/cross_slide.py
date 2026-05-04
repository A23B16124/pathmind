from backend.agents.base import BaseAgent
from backend.schemas.agents import CrossSlideInput, CrossSlideOutput
from backend.llm import chat

class CrossSlideAgent(BaseAgent):
    name = "cross_slide_aggregator"

    async def run(self, case_id: str, input_data: CrossSlideInput) -> CrossSlideOutput:
        await self.emit(case_id, "running", f"Synthese {len(input_data.slides)} lames")
        summary = "\n".join([f"Lame {s.slide_index}: {s.findings[:300]}" for s in input_data.slides])
        result = await chat(
            system="Tu es un expert en agregation multi-lames. Synthetise les findings: synthesis, dominant_pattern, affected_slides (list[int]), confidence (0-1).",
            messages=[{"role": "user", "content": summary}],
        )
        await self.emit(case_id, "done", result)
        return CrossSlideOutput(synthesis=result, confidence=0.87)
