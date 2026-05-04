from backend.agents.base import BaseAgent
from backend.schemas.agents import TileTriageInput, TileTriageOutput
from backend.llm import chat
from backend.prompts import load_prompt


class TileTriageAgent(BaseAgent):
    name = "tile_triage"

    async def run(self, case_id: str, input_data: TileTriageInput) -> TileTriageOutput:
        await self.emit(case_id, "running", f"Analyse lame {input_data.slide_index}", {"slide": input_data.slide_index})
        user = (
            f"Slide index: {input_data.slide_index}\n"
            f"Slide path: {input_data.slide_path}\n"
            f"Virchow2 patch embeddings: 1280-dim, statistical summary unavailable in current pass.\n"
            f"Task: identify up to 8 priority ROIs and exclude artifacts. Output the JSON schema only."
        )
        result = await chat(
            agent_name=self.name,
            system=load_prompt("tile_triage"),
            messages=[{"role": "user", "content": user}],
        )
        await self.emit(case_id, "done", result, {"slide": input_data.slide_index})
        return TileTriageOutput(slide_index=input_data.slide_index, confidence=0.85, summary=result)
