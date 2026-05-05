from backend.agents.base import BaseAgent
from backend.schemas.agents import HistopathologistInput, HistopathologistOutput
from backend.llm import chat
from backend.prompts import load_prompt


class HistopathologistAAgent(BaseAgent):
    name = "histopathologist_a"

    async def run(self, case_id: str, input_data: HistopathologistInput) -> HistopathologistOutput:
        await self.emit(case_id, "running", f"Histo-A (Qwen72B) analyzing slide {input_data.slide_index}", {"slide": input_data.slide_index})

        user = (
            f"Slide index: {input_data.slide_index}\n"
            f"Slide path: {input_data.slide_path}\n"
            f"Regions of interest: {input_data.regions_of_interest}\n\n"
            f"Perform full histopathological analysis. Output JSON only."
        )

        result = await chat(
            agent_name=self.name,
            model_key="qwen72b",
            system=load_prompt("histopathologist"),
            messages=[{"role": "user", "content": user}],
            max_tokens=2500,
        )

        await self.emit(case_id, "done", result, {"slide": input_data.slide_index})
        return HistopathologistOutput(
            slide_index=input_data.slide_index,
            agent_id="histo_a",
            model_used="qwen72b",
            findings=result,
            confidence=0.88,
            raw_json=result,
        )
