"""
Histopathologist-A — primary read using a vision-capable LLM (Qwen2.5-VL on MI300X,
Anthropic vision in dev). Receives real H&E image patches extracted from ROIs.

Falls back to text-only if patch extraction fails (e.g. WSI parse error upstream).
"""

from __future__ import annotations

import asyncio
import io
import json

from PIL import Image

from backend.agents.base import BaseAgent
from backend.schemas.agents import HistopathologistInput, HistopathologistOutput
from backend.llm import chat, build_user_message, encode_image_b64
from backend.prompts import load_prompt
from backend.wsi.loader import read_region_jpeg, WSILoadError

MAX_PATCHES_PER_SLIDE = 4
PATCH_PIXEL_SIZE = 1024


def _parse_confidence(raw: str) -> float | None:
    """Extract the LLM's self-reported confidence from a JSON-ish response."""
    if not raw:
        return None
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[-1]
        if s.lstrip().startswith("json"):
            s = s.lstrip()[4:]
        s = s.rsplit("```", 1)[0]
    try:
        d = json.loads(s)
        c = d.get("confidence")
        if isinstance(c, (int, float)):
            return max(0.0, min(1.0, float(c)))
    except Exception:
        pass
    return None
# Task 3: hard limits to stay within LLM context
MAX_PATCH_BYTES = 1 * 1024 * 1024   # 1 MB
MAX_PATCH_SIDE = 2048                # px


def _downscale_if_needed(jpeg: bytes) -> bytes:
    """Downscale JPEG until it fits MAX_PATCH_BYTES and MAX_PATCH_SIDE."""
    if len(jpeg) <= MAX_PATCH_BYTES:
        img = Image.open(io.BytesIO(jpeg))
        if max(img.size) <= MAX_PATCH_SIDE:
            return jpeg
    img = Image.open(io.BytesIO(jpeg)).convert("RGB")
    # Cap dimensions first
    if max(img.size) > MAX_PATCH_SIDE:
        img.thumbnail((MAX_PATCH_SIDE, MAX_PATCH_SIDE), Image.LANCZOS)
    # Then iterate quality down until size fits
    for quality in (80, 70, 60, 50, 40):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        data = buf.getvalue()
        if len(data) <= MAX_PATCH_BYTES:
            return data
    return data  # best effort even if slightly over


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
            jpeg = _downscale_if_needed(jpeg)
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

        clinical_block = (
            f"=== CLINICAL CONTEXT (anchor your analysis to this) ===\n{input_data.clinical_context}\n\n"
            if input_data.clinical_context else ""
        )
        text = (
            f"{clinical_block}"
            f"Slide index: {input_data.slide_index}\n"
            f"ROIs (level-0 px): {json.dumps(roi_summary)}\n"
            f"Image patches attached: {len(patches)}\n\n"
            f"Examine each patch IN LIGHT OF THE CLINICAL CONTEXT ABOVE and produce full "
            f"histopathological analysis (organ-appropriate diagnoses, differential, grading). "
            f"Do NOT diagnose pathologies inconsistent with the indicated organ/site. "
            f"Output JSON only."
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
        # Use the model's own confidence when parseable.  If patches=0, the
        # agent literally has no visual data — clamp the ceiling so we don't
        # propagate fake high confidence into the chief debate.
        confidence = _parse_confidence(result)
        if confidence is None:
            confidence = 0.0 if result.startswith("[LLM") else 0.5
        if not patches:
            confidence = min(confidence, 0.2)
        return HistopathologistOutput(
            slide_index=input_data.slide_index,
            agent_id="histo_a",
            model_used="qwen72b",
            findings=result,
            confidence=confidence,
            raw_json=result,
        )
