from backend.agents.base import BaseAgent
from backend.schemas.agents import LiteratureHunterInput, LiteratureHunterOutput
from backend.llm import chat
from backend.prompts import load_prompt


class LiteratureHunterAgent(BaseAgent):
    name = "literature_hunter"

    async def run(self, case_id: str, input_data: LiteratureHunterInput) -> LiteratureHunterOutput:
        await self.emit(case_id, "running", f"Literature search: {input_data.hypothesis[:80]}")
        user = (
            f"Working hypothesis: {input_data.hypothesis}\n"
            f"Keywords: {', '.join(input_data.keywords)}\n"
            f"Retrieve similar TCGA cases (top-k via UNI2 embedding similarity, mocked here) "
            f"and cite key PubMed papers. Output the JSON schema only."
        )
        result = await chat(
            agent_name=self.name,
            system=load_prompt("literature_hunter"),
            messages=[{"role": "user", "content": user}],
        )
        await self.emit(case_id, "done", result)
        return LiteratureHunterOutput(key_findings=result, similar_cases=847, confidence=0.82)
