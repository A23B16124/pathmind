from backend.agents.base import BaseAgent
from backend.schemas.agents import HistopathologistInput, HistopathologistOutput
from backend.llm import chat
from backend.prompts import load_prompt


class HistopathologistBAgent(BaseAgent):
    name = "histopathologist_b"

    async def run(self, case_id: str, input_data: HistopathologistInput) -> HistopathologistOutput:
        await self.emit(case_id, "running", f"Histo-B (Meditron70B) second read slide {input_data.slide_index}", {"slide": input_data.slide_index})

        user = (
            f"Slide index: {input_data.slide_index}\n"
            f"Slide path: {input_data.slide_path}\n"
            f"Regions of interest: {input_data.regions_of_interest}\n\n"
            f"Provide your independent second-read analysis. Output JSON only."
        )

        result = await chat(
            agent_name=self.name,
            model_key="meditron70b",
            system=load_prompt("histopathologist_b"),
            messages=[{"role": "user", "content": user}],
            max_tokens=2500,
        )

        await self.emit(case_id, "done", result, {"slide": input_data.slide_index})
        return HistopathologistOutput(
            slide_index=input_data.slide_index,
            agent_id="histo_b",
            model_used="meditron70b",
            findings=result,
            confidence=0.84,
            raw_json=result,
        )
