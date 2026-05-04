from backend.agents.base import BaseAgent
from backend.schemas.agents import HistopathologistInput, HistopathologistOutput
from backend.llm import chat

class HistopathologistAgent(BaseAgent):
    name = "histopathologist"

    async def run(self, case_id: str, input_data: HistopathologistInput) -> HistopathologistOutput:
        await self.emit(case_id, "running", f"Analyse histologique lame {input_data.slide_index}", {"slide": input_data.slide_index})
        result = await chat(
            system="Tu es un histopathologiste expert. Analyse la lame et fournis: findings (description detaillee), grade (I/II/III), mitotic_index, margin_status, confidence (0-1).",
            messages=[{"role": "user", "content": f"Lame {input_data.slide_index}, ROIs: {input_data.regions_of_interest}"}],
        )
        await self.emit(case_id, "done", result, {"slide": input_data.slide_index})
        return HistopathologistOutput(slide_index=input_data.slide_index, findings=result, confidence=0.88)
