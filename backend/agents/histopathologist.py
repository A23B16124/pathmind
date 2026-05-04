from backend.agents.base import BaseAgent
from backend.schemas.agents import HistopathologistInput, HistopathologistOutput
from backend.llm import chat
from backend.prompts import load_prompt


class HistopathologistAgent(BaseAgent):
    name = "histopathologist"

    async def run(self, case_id: str, input_data: HistopathologistInput) -> HistopathologistOutput:
        await self.emit(case_id, "running", f"Histopath analysis slide {input_data.slide_index}", {"slide": input_data.slide_index})
        user = (
            f"Slide index: {input_data.slide_index}\n"
            f"Slide path: {input_data.slide_path}\n"
            f"ROIs from Tile-Triage: {input_data.regions_of_interest}\n"
            f"UNI2 slide-level embedding: 1024-dim, mock summary in this pass.\n"
            f"Task: produce a detailed histopathological analysis. Output the JSON schema only."
        )
        result = await chat(
            agent_name=self.name,
            system=load_prompt("histopathologist"),
            messages=[{"role": "user", "content": user}],
        )
        await self.emit(case_id, "done", result, {"slide": input_data.slide_index})
        return HistopathologistOutput(slide_index=input_data.slide_index, findings=result, confidence=0.88)
