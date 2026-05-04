from backend.agents.base import BaseAgent
from backend.schemas.agents import TileTriageInput, TileTriageOutput
from backend.llm import chat

class TileTriageAgent(BaseAgent):
    name = "tile_triage"

    async def run(self, case_id: str, input_data: TileTriageInput) -> TileTriageOutput:
        await self.emit(case_id, "running", f"Analyse lame {input_data.slide_index}")
        result = await chat(
            system="Tu es un agent de triage de lames histologiques. Identifie les zones tumorales prioritaires. Reponds en JSON avec: regions_of_interest (list de dict x,y,w,h,priority), tile_count (int), summary (str), confidence (float 0-1).",
            messages=[{"role": "user", "content": f"Lame {input_data.slide_index}: {input_data.slide_path}"}],
        )
        await self.emit(case_id, "done", result, {"slide": input_data.slide_index})
        return TileTriageOutput(slide_index=input_data.slide_index, confidence=0.85, summary=result)
