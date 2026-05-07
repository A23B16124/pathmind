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
from backend.agents.histopathologist_a import _extract_patches, MAX_PATCHES_PER_SLIDE, _parse_confidence
from backend.prompts import load_prompt


class HistopathologistBAgent(BaseAgent):
    name = "histopathologist_b"

    async def run(self, case_id: str, input_data: HistopathologistInput) -> HistopathologistOutput:
        await self.emit(
            case_id, "running",
            f"Histo-B (Meditron-70B) second read slide {input_data.slide_index}",
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
        roi_ids_list = ", ".join(r["id"] for r in roi_summary)
        text = (
            f"{clinical_block}"
            f"Slide index: {input_data.slide_index}\n"
            f"ROIs ({len(roi_summary)} total) - analyze EACH separately: {json.dumps(roi_summary)}\n"
            f"Image patches attached: {len(patches)} (same order: {roi_ids_list})\n\n"
            f"For EACH of the {len(roi_summary)} ROIs, produce a separate entry in per_roi array using its EXACT roi_id. "
            f"Different ROIs MUST have differentiated findings if histology differs. "
            f"Provide your independent second-read analysis IN LIGHT OF THE CLINICAL CONTEXT - "
            f"challenge the dominant pattern but stay consistent with the indicated organ/site. "
            f"Output JSON only matching the schema."
        )

        # Groq doesn't support vision — send text-only (no image patches for Histo-B)
        user_msg = build_user_message(text, images_b64=None, backend="openai")

        result = await chat(
            agent_name=self.name,
            model_key="meditron70b",
            system=load_prompt("histopathologist_b"),
            messages=[user_msg],
            max_tokens=4000,
            timeout=180.0,
        )

        await self.emit(
            case_id, "done",
            result if not result.startswith("[LLM") else f"Histo-B error: {result}",
            {"slide": input_data.slide_index, "patches_seen": len(patches)},
        )
        # Histo-B is text-only (Groq Llama, no vision).  Confidence ceiling
        # depends on whether triage actually found any ROIs to describe.
        confidence = _parse_confidence(result)
        if confidence is None:
            confidence = 0.0 if result.startswith("[LLM") else 0.5
        if not input_data.regions_of_interest:
            confidence = min(confidence, 0.2)
        return HistopathologistOutput(
            slide_index=input_data.slide_index,
            agent_id="histo_b",
            model_used="llama-3.3-70b-versatile",
            findings=result,
            confidence=confidence,
            raw_json=result,
        )
