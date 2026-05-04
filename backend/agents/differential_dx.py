from backend.agents.base import BaseAgent
from backend.schemas.agents import DifferentialDxInput, DifferentialDxOutput
from backend.llm import chat
from backend.prompts import load_prompt


class DifferentialDxAgent(BaseAgent):
    name = "differential_diagnostician"

    async def run(self, case_id: str, input_data: DifferentialDxInput) -> DifferentialDxOutput:
        await self.emit(case_id, "running", "Etablissement diagnostics differentiels")
        user = (
            f"Cross-slide synthesis:\n{input_data.cross_slide.synthesis}\n\n"
            f"Literature context:\n{input_data.literature.key_findings}\n\n"
            f"Clinical data: {input_data.clinical_data}\n\n"
            f"Task: rank 3-5 differential diagnoses with probabilities, ICD-O code, "
            f"pT/pN staging, supporting evidence and discriminating features. "
            f"Output the JSON schema only."
        )
        result = await chat(
            agent_name=self.name,
            system=load_prompt("differential_diagnostician"),
            messages=[{"role": "user", "content": user}],
            max_tokens=2500,
        )
        await self.emit(case_id, "done", result)
        return DifferentialDxOutput(primary_diagnosis=result, confidence=0.91)
