"""
Histopathologist-B — independent second read via Groq (Llama 3.3 70B).

Histo-A runs on Qwen2.5-VL-72B (local vLLM on MI300X). Histo-B calls
Groq Llama 3.3 70B — a genuinely different model family (Meta vs Alibaba),
different training corpus, different architecture. Real second opinion.
"""

from __future__ import annotations

import asyncio
import json

from backend.agents.base import BaseAgent
from backend.schemas.agents import HistopathologistInput, HistopathologistOutput
from backend.llm import chat, build_user_message
from backend.agents.histopathologist_a import _extract_patches, MAX_PATCHES_PER_SLIDE
from backend.prompts import load_prompt


class HistopathologistBAgent(BaseAgent):
    name = "histopathologist_b"

    async def run(self, case_id: str, input_data: HistopathologistInput) -> HistopathologistOutput:
        await self.emit(
            case_id, "running",
            f"Histo-B (Groq Llama-3.3-70B) second read slide {input_data.slide_index}",
            {"slide": input_data.slide_index},
        )

        patches: list[str] = await asyncio.to_thread(
            _extract_patches, input_data.slide_path, input_data.regions_of_interest,
        )

        roi_summary = [
            {"id": r.get("roi_id"), "tissue": round(r.get("tissue_fraction", 0), 2),
             "x": r.get("x_px"), "y": r.get("y_px")}
            for r in input_data.regions_of_interest[:MAX_PATCHES_PER_SLIDE]
        ]

        clinical_block = (
            f"=== CLINICAL CONTEXT (anchor your analysis to this) ===\n{input_data.clinical_context}\n\n"
            if input_data.clinical_context else ""
        )
        text = (
            f"{clinical_block}"
            f"Slide index: {input_data.slide_index}\n"
            f"ROIs (level-0 px): {json.dumps(roi_summary)}\n"
            f"Image patches attached: {len(patches)}\n\n"
            f"Provide your independent second-read analysis IN LIGHT OF THE CLINICAL CONTEXT — "
            f"challenge the dominant pattern but stay consistent with the indicated organ/site. "
            f"Output JSON only."
        )

        # Groq doesn't support vision — send text-only (no image patches for Histo-B)
        user_msg = build_user_message(text, images_b64=None, backend="openai")

        result = await chat(
            agent_name=self.name,
            model_key="groq",
            system=load_prompt("histopathologist_b"),
            messages=[user_msg],
            max_tokens=2500,
        )

        await self.emit(
            case_id, "done",
            result if not result.startswith("[LLM") else f"Histo-B error: {result}",
            {"slide": input_data.slide_index, "patches_seen": len(patches)},
        )
        confidence = 0.0 if result.startswith("[LLM") else 0.84
        return HistopathologistOutput(
            slide_index=input_data.slide_index,
            agent_id="histo_b",
            model_used="llama-3.3-70b-versatile",
            findings=result,
            confidence=confidence,
            raw_json=result,
        )
