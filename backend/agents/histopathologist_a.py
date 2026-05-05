"""
Histopathologist-A — primary read using a vision-capable LLM (Qwen2.5-VL on MI300X,
Anthropic vision in dev). Receives real H&E image patches extracted from ROIs.

Falls back to text-only if patch extraction fails (e.g. WSI parse error upstream).
"""

from __future__ import annotations

import asyncio
import json

from backend.agents.base import BaseAgent
from backend.schemas.agents import HistopathologistInput, HistopathologistOutput
from backend.llm import chat, build_user_message, encode_image_b64
from backend.prompts import load_prompt
from backend.wsi.loader import read_region_jpeg, WSILoadError

# Cap how many patches we send to the LLM per slide (cost + context budget)
MAX_PATCHES_PER_SLIDE = 4
PATCH_PIXEL_SIZE = 1024  # output JPEG side, downsampled from level-0 region


def _extract_patches(slide_path: str, rois: list[dict]) -> list[str]:
    """Extract up to MAX_PATCHES_PER_SLIDE JPEG patches as base64 strings."""
    patches: list[str] = []
    for roi in rois[:MAX_PATCHES_PER_SLIDE]:
        try:
            jpeg = read_region_jpeg(
                slide_path,
                roi["x_px"], roi["y_px"],
                min(roi["width_px"], PATCH_PIXEL_SIZE),
                min(roi["height_px"], PATCH_PIXEL_SIZE),
                level=0,
                quality=85,
            )
            patches.append(encode_image_b64(jpeg))
        except (WSILoadError, KeyError, OSError):
            continue
    return patches


class HistopathologistAAgent(BaseAgent):
    name = "histopathologist_a"

    async def run(self, case_id: str, input_data: HistopathologistInput) -> HistopathologistOutput:
        await self.emit(
            case_id, "running",
            f"Histo-A (Qwen 72B VL) analyzing slide {input_data.slide_index}",
            {"slide": input_data.slide_index},
        )

        patches = await asyncio.to_thread(_extract_patches, input_data.slide_path, input_data.regions_of_interest)

        roi_summary = [
            {"id": r.get("roi_id"), "tissue": round(r.get("tissue_fraction", 0), 2),
             "x": r.get("x_px"), "y": r.get("y_px")}
            for r in input_data.regions_of_interest[:MAX_PATCHES_PER_SLIDE]
        ]

        text = (
            f"Slide index: {input_data.slide_index}\n"
            f"ROIs (level-0 px): {json.dumps(roi_summary)}\n"
            f"Image patches attached: {len(patches)}\n\n"
            f"Examine each patch and produce full histopathological analysis. Output JSON only."
        )

        user_msg = build_user_message(text, images_b64=patches)

        result = await chat(
            agent_name=self.name,
            model_key="qwen72b",
            system=load_prompt("histopathologist"),
            messages=[user_msg],
            max_tokens=2500,
        )

        await self.emit(
            case_id, "done",
            result if not result.startswith("[LLM") else f"Histo-A error: {result}",
            {"slide": input_data.slide_index, "patches_seen": len(patches)},
        )
        confidence = 0.0 if result.startswith("[LLM") else 0.88
        return HistopathologistOutput(
            slide_index=input_data.slide_index,
            agent_id="histo_a",
            model_used="qwen72b",
            findings=result,
            confidence=confidence,
            raw_json=result,
        )
