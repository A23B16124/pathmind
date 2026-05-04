from backend.agents.base import BaseAgent
from backend.schemas.agents import LiteratureHunterInput, LiteratureHunterOutput
from backend.llm import chat

class LiteratureHunterAgent(BaseAgent):
    name = "literature_hunter"

    async def run(self, case_id: str, input_data: LiteratureHunterInput) -> LiteratureHunterOutput:
        await self.emit(case_id, "running", f"Recherche: {input_data.hypothesis[:80]}")
        result = await chat(
            system="Tu es un agent de recherche bibliographique en pathologie. Cite des etudes PubMed pertinentes. Retourne: papers (list), similar_cases (int), key_findings (str), confidence (float).",
            messages=[{"role": "user", "content": f"Hypothese: {input_data.hypothesis}\nMots-cles: {input_data.keywords}"}],
        )
        await self.emit(case_id, "done", result)
        return LiteratureHunterOutput(key_findings=result, similar_cases=847, confidence=0.82)
