import json
from backend.agents.base import BaseAgent
from backend.schemas.agents import ChiefInput, ChiefOutput, DebateRound
from backend.llm import chat
from backend.prompts import load_prompt


class ChiefAgent(BaseAgent):
    name = "chief"

    async def run(self, case_id: str, input_data: ChiefInput) -> ChiefOutput:
        await self.emit(case_id, "running", "Chief reviewing dual-read findings")

        disagreements = input_data.cross_slide.disagreements
        if disagreements:
            await self.emit(
                case_id,
                "running",
                f"Debate: {len(disagreements)} disagreement(s) identified — arbitrating",
            )

        user = (
            f"Patient ID: {input_data.patient_id}\n"
            f"Clinical data: {json.dumps(input_data.clinical_data)}\n\n"
            f"=== HISTO-A SYNTHESIS (Qwen2.5-72B) ===\n{input_data.cross_slide.synthesis_a}\n\n"
            f"=== HISTO-B SYNTHESIS (Meditron-70B) ===\n{input_data.cross_slide.synthesis_b}\n\n"
            f"=== IDENTIFIED DISAGREEMENTS ===\n"
            + ("\n".join(f"- {d}" for d in disagreements) if disagreements else "None — readings concordant")
            + f"\n\n=== LITERATURE CONTEXT ===\n{input_data.literature.key_findings}\n"
            f"Similar cases: {input_data.literature.similar_cases}\n\n"
            f"Task: (1) Simulate debate for each disagreement (histo_a argues, histo_b argues, you arbitrate). "
            f"(2) Produce final CAP report JSON. Output JSON only."
        )

        result = await chat(
            agent_name=self.name,
            model_key="qwen72b",
            system=load_prompt("chief"),
            messages=[{"role": "user", "content": user}],
            max_tokens=4000,
        )

        await self.emit(case_id, "done", result)

        try:
            data = json.loads(result)
        except Exception:
            data = {}

        rounds = [
            DebateRound(
                agent_id=r.get("agent_id", ""),
                argument=r.get("argument", ""),
                conceded=r.get("conceded", False),
            )
            for r in data.get("debate_rounds", [])
        ]

        return ChiefOutput(
            debate_rounds=rounds,
            debate_summary=data.get("debate_summary", ""),
            diagnosis=data.get("primary_diagnosis", ""),
            biomarkers=data.get("biomarkers", []),
            confidence=float(data.get("confidence", 0.92)),
            cap_report=data,
        )
