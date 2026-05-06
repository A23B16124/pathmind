"""
Tile Triage agent.

Now performs REAL WSI processing:
  1. Opens the slide with OpenSlide → metadata.
  2. Runs tissue mask + grid sampling → ROI candidates.
  3. Optionally enriches ROIs via LLM (priority + reasoning) — best-effort.

If WSI parsing fails (missing file, missing libopenslide), the agent returns
an empty ROI list with parse_failed=True instead of crashing the pipeline.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from backend.agents.base import BaseAgent
from backend.schemas.agents import TileTriageInput, TileTriageOutput
from backend.wsi.loader import open_slide, WSILoadError
from backend.wsi.tiler import select_rois, normalize_roi
from backend.vision.foundation_embeds import embed_rois


class TileTriageAgent(BaseAgent):
    name = "tile_triage"

    async def run(self, case_id: str, input_data: TileTriageInput) -> TileTriageOutput:
        await self.emit(
            case_id, "running",
            f"Triaging slide {input_data.slide_index}",
            {"slide": input_data.slide_index},
        )

        # Resolve the slide path to an actual file on disk.
        # input_data.slide_path may be a TCGA path like
        # "tcga/TCGA-44-2657-01Z-00-DX1.<uuid>.svs" that doesn't exist locally.
        # _find_slide_wsi() applies the same fallback logic as the thumbnail
        # endpoint so UNI2/Virchow2 run on real tissue instead of failing.
        from backend.api.slides import _find_slide_wsi  # local import avoids circular dep

        slide_id = Path(input_data.slide_path).stem
        resolved = await asyncio.to_thread(_find_slide_wsi, slide_id)
        actual_path = str(resolved) if resolved is not None else input_data.slide_path

        try:
            meta = await asyncio.to_thread(open_slide, actual_path)
            rois = await asyncio.to_thread(
                select_rois,
                actual_path,
                2048,   # target tile px (level-0)
                8,      # max ROIs
                0.30,   # min tissue fraction
            )
        except WSILoadError as e:
            await self.emit(
                case_id, "error",
                f"WSI load failed: {e}",
                {"slide": input_data.slide_index},
            )
            return TileTriageOutput(
                slide_index=input_data.slide_index,
                slide_path=input_data.slide_path,
                summary=f"WSI load failed: {e}",
                parse_failed=True,
                confidence=0.0,
            )

        roi_dicts = []
        for r in rois:
            d = normalize_roi(r, meta.width, meta.height)
            d.update({
                "x_px": r.x,
                "y_px": r.y,
                "width_px": r.width,
                "height_px": r.height,
                "level": r.level,
            })
            roi_dicts.append(d)

        summary_payload = {
            "slide_index": input_data.slide_index,
            "dimensions": [meta.width, meta.height],
            "objective": meta.objective_power,
            "mpp": meta.mpp_x,
            "vendor": meta.vendor,
            "rois": [
                {
                    "roi_id": d["roi_id"],
                    "tissue_fraction": round(d["tissue_fraction"], 3),
                    "x": d["x_px"], "y": d["y_px"],
                    "w": d["width_px"], "h": d["height_px"],
                }
                for d in roi_dicts
            ],
        }
        summary_str = json.dumps(summary_payload, ensure_ascii=False)

        # Emit normalized ROI coords so the frontend can draw overlays.
        overlay_payload = [
            {
                "x": d["x"], "y": d["y"], "w": d["w"], "h": d["h"],
                "label": f"{d['roi_id']} ({d['tissue_fraction']*100:.0f}%)",
                "tissue": d["tissue_fraction"],
            }
            for d in roi_dicts
        ]

        # Foundation-model embeddings — UNI2-h (pathology ViT-G/14) and
        # Virchow2 (ViT-H/14) on the same MI300X. We POST patches at the
        # ROI centers and surface stats; if the embed service is down we
        # silently skip — the pipeline still runs on the LLM agents alone.
        embed_stats = await embed_rois(meta.path, rois) if rois else None
        if embed_stats and embed_stats.get("uni2") and embed_stats.get("virchow2"):
            uni2 = embed_stats["uni2"]
            virchow = embed_stats["virchow2"]
            await self.emit(
                case_id, "running",
                f"Foundation models: UNI2-h ({uni2['n']}×{uni2['dim']}) + "
                f"Virchow2 ({virchow['n']}×{virchow['dim']}) — "
                f"avg cos-sim {uni2['mean_cos_sim']}/{virchow['mean_cos_sim']}",
                {"slide": input_data.slide_index, "embed_stats": embed_stats},
            )

        await self.emit(
            case_id, "done",
            f"Slide {input_data.slide_index}: {len(rois)} ROIs ({meta.width}x{meta.height}, {meta.objective_power or '?'}x)",
            {
                "slide": input_data.slide_index,
                "rois_count": len(rois),
                "rois": overlay_payload,
                "slide_dims": [meta.width, meta.height],
                "foundation_embeds": embed_stats,
            },
        )

        confidence = 0.85 if rois else 0.4
        return TileTriageOutput(
            slide_index=input_data.slide_index,
            slide_path=meta.path,
            slide_width=meta.width,
            slide_height=meta.height,
            mpp_x=meta.mpp_x,
            objective_power=meta.objective_power,
            regions_of_interest=roi_dicts,
            tile_count=len(rois),
            confidence=confidence,
            summary=summary_str,
        )
