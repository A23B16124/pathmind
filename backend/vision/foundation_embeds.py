"""
Foundation model embeddings — wires UNI2-h and Virchow2 (served by the embed
service on port 8001) into the tile-triage pipeline.

Both models are pathology-foundation ViTs hosted on AMD MI300X via vLLM-style
HTTP inference. We extract a 224x224 patch at the center of each ROI, POST a
batch to /embed once per model, and surface stats (count, dim, mean cosine
similarity) so downstream agents — and the demo viewer — see the foundation
models doing real work, not just mocked context.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
import numpy as np

EMBED_BASE_URL = os.getenv("EMBED_BASE_URL", "http://localhost:8001")
PATCH_SIZE = 224  # ViT input size for both UNI2-h and Virchow2


def _read_patches(slide_path: str, rois: list[Any]) -> np.ndarray:
    """Read one 224x224 RGB patch at the center of each ROI. Returns (N,224,224,3) uint8."""
    from openslide import OpenSlide
    slide = OpenSlide(slide_path)
    try:
        patches = []
        for r in rois:
            cx = r.x + r.width // 2 - PATCH_SIZE // 2
            cy = r.y + r.height // 2 - PATCH_SIZE // 2
            cx = max(0, min(slide.dimensions[0] - PATCH_SIZE, cx))
            cy = max(0, min(slide.dimensions[1] - PATCH_SIZE, cy))
            tile = slide.read_region((cx, cy), 0, (PATCH_SIZE, PATCH_SIZE)).convert("RGB")
            patches.append(np.asarray(tile, dtype=np.uint8))
        return np.stack(patches) if patches else np.zeros((0, PATCH_SIZE, PATCH_SIZE, 3), dtype=np.uint8)
    finally:
        slide.close()


async def _post_embed(client: httpx.AsyncClient, model: str, tiles: list) -> dict | None:
    try:
        r = await client.post(
            f"{EMBED_BASE_URL}/embed",
            json={"model": model, "tiles": tiles, "batch_size": 8},
            timeout=60.0,
        )
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


async def embed_rois(slide_path: str, rois: list[Any]) -> dict:
    """Run UNI2 + Virchow2 on the ROI patches, return summary stats.

    Both calls run concurrently. Returns:
        { uni2: {n, dim, mean_cos_sim}, virchow2: {n, dim, mean_cos_sim},
          patches: int, model: 'UNI2-h+Virchow2' }
    On any failure the corresponding entry is None — pipeline never crashes.
    """
    if not rois:
        return {"patches": 0, "uni2": None, "virchow2": None}

    patches = await asyncio.to_thread(_read_patches, slide_path, rois)
    if patches.shape[0] == 0:
        return {"patches": 0, "uni2": None, "virchow2": None}

    tiles_list = patches.tolist()
    async with httpx.AsyncClient() as client:
        uni2_resp, virchow_resp = await asyncio.gather(
            _post_embed(client, "uni2", tiles_list),
            _post_embed(client, "virchow2", tiles_list),
        )

    def _stats(resp: dict | None) -> dict | None:
        if not resp or "embeddings" not in resp:
            return None
        emb = np.asarray(resp["embeddings"], dtype=np.float32)
        if emb.ndim != 2 or emb.shape[0] == 0:
            return None
        # Normalise rows then take pairwise cos sim mean (excluding diagonal)
        norms = np.linalg.norm(emb, axis=1, keepdims=True) + 1e-8
        unit = emb / norms
        sim = unit @ unit.T
        n = sim.shape[0]
        if n > 1:
            mask = ~np.eye(n, dtype=bool)
            mean_cos = float(sim[mask].mean())
        else:
            mean_cos = 1.0
        return {"n": int(emb.shape[0]), "dim": int(emb.shape[1]), "mean_cos_sim": round(mean_cos, 3)}

    return {
        "patches": int(patches.shape[0]),
        "uni2": _stats(uni2_resp),
        "virchow2": _stats(virchow_resp),
        "model": "UNI2-h + Virchow2",
    }
