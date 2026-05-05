import json
from backend.agents.base import BaseAgent
from backend.schemas.agents import CrossSlideInput, CrossSlideOutput
from backend.llm import chat
from backend.prompts import load_prompt


class CrossSlideAgent(BaseAgent):
    name = "cross_slide_aggregator"

    async def run(self, case_id: str, input_data: CrossSlideInput) -> CrossSlideOutput:
        n_slides = len(input_data.slides_a)
        await self.emit(
            case_id,
            "running",
            f"Aggregating {n_slides} slides x2 reads — detecting disagreements",
        )

        findings_a = "\n".join(
            f"Slide {s.slide_index}: {s.findings[:600]}" for s in input_data.slides_a
        )
        findings_b = "\n".join(
            f"Slide {s.slide_index}: {s.findings[:600]}" for s in input_data.slides_b
        )

        user = (
            f"Patient: {input_data.patient_id}\n"
            f"Slides analyzed: {n_slides} (each read independently by Histo-A and Histo-B)\n\n"
            f"=== HISTO-A READINGS (Qwen2.5-72B) ===\n{findings_a}\n\n"
            f"=== HISTO-B READINGS (Meditron-70B) ===\n{findings_b}\n\n"
            f"Task: (1) Synthesize each reader's cross-slide view (synthesis_a, synthesis_b). "
            f"(2) Identify SPECIFIC disagreements between A and B (grade, margin, LVI, PNI, dominant pattern, biomarker recommendations). "
            f"(3) State the dominant pattern (consensus or A's view if no consensus). "
            f"(4) List affected slide indices. "
            f"Output JSON only with keys: synthesis_a, synthesis_b, dominant_pattern, affected_slides (list of int), disagreements (list of strings)."
        )

        result = await chat(
            agent_name=self.name,
            model_key="qwen72b",
            system=load_prompt("cross_slide_aggregator"),
            messages=[{"role": "user", "content": user}],
            max_tokens=2500,
        )

        await self.emit(case_id, "done", result)

        # Strip markdown fences
        raw = result.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip().rstrip("`").strip()

        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}

        return CrossSlideOutput(
            synthesis_a=data.get("synthesis_a", result),
            synthesis_b=data.get("synthesis_b", ""),
            dominant_pattern=data.get("dominant_pattern", ""),
            affected_slides=data.get("affected_slides", []),
            disagreements=data.get("disagreements", []),
            confidence=0.89,
        )
