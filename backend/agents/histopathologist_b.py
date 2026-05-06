"""
Histopathologist-B — independent second read.

Meditron-70B is text-only (no vision capability). To still benefit from real
pixels rather than coordinate text, we attach patches when the active backend
supports vision (Anthropic dev / vLLM with a VL model). When the configured
backend is Meditron text-only, we serialize ROI tissue stats as text.
"""

from __future__ import annotations

import asyncio
import json
import os

from backend.agents.base import BaseAgent
from backend.schemas.agents import HistopathologistInput, HistopathologistOutput
from backend.llm import chat, build_user_message, LLM_BACKEND
from backend.agents.histopathologist_a import _extract_patches, MAX_PATCHES_PER_SLIDE
from backend.prompts import load_prompt


def _backend_supports_vision() -> bool:
    """Anthropic Claude is multimodal; vLLM only when configured to a VL model."""
    if LLM_BACKEND == "anthropic":
        return True
    vllm_model = os.getenv("VLLM_MODEL_MEDITRON", "")
    return "vl" in vllm_model.lower() or "vision" in vllm_model.lower()


class HistopathologistBAgent(BaseAgent):
    name = "histopathologist_b"

    async def run(self, case_id: str, input_data: HistopathologistInput) -> HistopathologistOutput:
        await self.emit(
            case_id, "running",
            f"Histo-B (Meditron 70B) second read slide {input_data.slide_index}",
            {"slide": input_data.slide_index},
        )

        patches: list[str] = []
        if _backend_supports_vision():
            patches = await asyncio.to_thread(
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

        user_msg = build_user_message(text, images_b64=patches)

        result = await chat(
            agent_name=self.name,
            model_key="meditron70b",
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
            model_used="meditron70b",
            findings=result,
            confidence=confidence,
            raw_json=result,
        )
