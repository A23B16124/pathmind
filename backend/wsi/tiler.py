"""
Tissue tiler — grid sampling + tissue-mask filtering.

Produces ROI candidates by:
  1. Generating a grid of tiles at a chosen level.
  2. Filtering by simple tissue mask (Otsu on a downsampled thumbnail).
  3. Returning ROIs sorted by tissue density.

Output ROIs are in level-0 coordinates so they are compatible with
read_region_jpeg() and frontend overlay normalization.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Optional

import numpy as np
from PIL import Image

from backend.wsi.loader import _OPENSLIDE_OK, _resolve_path, WSILoadError

if _OPENSLIDE_OK:
    from openslide import OpenSlide  # type: ignore
else:
    OpenSlide = None  # type: ignore


@dataclass
class TileROI:
    roi_id: str
    x: int                  # level-0 px
    y: int                  # level-0 px
    width: int              # level-0 px
    height: int             # level-0 px
    tissue_fraction: float  # 0..1
    level: int = 0          # extraction level (0 = native res)


def _otsu_threshold(gray: np.ndarray) -> int:
    """Pure-numpy Otsu threshold (no OpenCV/skimage dep)."""
    hist, _ = np.histogram(gray.ravel(), bins=256, range=(0, 256))
    total = gray.size
    if total == 0:
        return 128
    sum_total = float(np.sum(np.arange(256) * hist))
    sum_b = 0.0
    w_b = 0.0
    max_var = 0.0
    threshold = 128
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (sum_total - sum_b) / w_f
        var_between = w_b * w_f * (m_b - m_f) ** 2
        if var_between > max_var:
            max_var = var_between
            threshold = t
    return threshold


def _tissue_mask(thumb_rgb: np.ndarray) -> np.ndarray:
    """Boolean tissue mask from an RGB thumbnail. True = tissue."""
    gray = np.mean(thumb_rgb, axis=2).astype(np.uint8)
    thr = _otsu_threshold(gray)
    # Tissue is darker than background; bg is usually ~white (>200).
    return gray < min(thr, 220)


def select_rois(
    slide_path: str,
    target_tile_px: int = 2048,
    max_rois: int = 8,
    min_tissue_fraction: float = 0.3,
) -> list[TileROI]:
    """
    Tile the slide on a regular grid (level-0 coords) and keep tiles whose
    tissue fraction exceeds `min_tissue_fraction`. Returns top-N by tissue density.

    Falls back to a centered ROI if no tissue is detected (or openslide fails).
    """
    if not _OPENSLIDE_OK:
        raise WSILoadError("openslide not available")

    resolved = _resolve_path(slide_path)
    if resolved is None:
        raise WSILoadError(f"slide not found: {slide_path}")

    slide = OpenSlide(str(resolved))
    try:
        w0, h0 = slide.dimensions

        # Thumbnail size capped at 2k per side — tissue mask is approximate.
        thumb_max = 2048
        scale = max(w0, h0) / thumb_max
        scale = max(scale, 1.0)
        tw, th = int(w0 / scale), int(h0 / scale)
        thumb = slide.get_thumbnail((tw, th)).convert("RGB")
        thumb_arr = np.asarray(thumb)
        mask = _tissue_mask(thumb_arr)

        # Walk a grid over the thumbnail in tile-sized cells.
        cell_thumb_px = max(int(target_tile_px / scale), 8)
        candidates: list[TileROI] = []
        idx = 0
        for ty in range(0, mask.shape[0], cell_thumb_px):
            for tx in range(0, mask.shape[1], cell_thumb_px):
                y_end = min(ty + cell_thumb_px, mask.shape[0])
                x_end = min(tx + cell_thumb_px, mask.shape[1])
                cell = mask[ty:y_end, tx:x_end]
                if cell.size == 0:
                    continue
                tissue_frac = float(cell.mean())
                if tissue_frac < min_tissue_fraction:
                    continue

                x0 = int(tx * scale)
                y0 = int(ty * scale)
                # Clip to slide bounds
                tile_w = min(target_tile_px, w0 - x0)
                tile_h = min(target_tile_px, h0 - y0)
                if tile_w <= 0 or tile_h <= 0:
                    continue

                idx += 1
                candidates.append(TileROI(
                    roi_id=f"roi_{idx:03d}",
                    x=x0,
                    y=y0,
                    width=tile_w,
                    height=tile_h,
                    tissue_fraction=tissue_frac,
                ))

        candidates.sort(key=lambda r: r.tissue_fraction, reverse=True)
        if not candidates:
            # fallback: centered tile
            cx = max(0, (w0 - target_tile_px) // 2)
            cy = max(0, (h0 - target_tile_px) // 2)
            candidates.append(TileROI(
                roi_id="roi_center",
                x=cx, y=cy,
                width=min(target_tile_px, w0),
                height=min(target_tile_px, h0),
                tissue_fraction=0.0,
            ))

        return candidates[:max_rois]
    finally:
        slide.close()


def normalize_roi(roi: TileROI, slide_width: int, slide_height: int) -> dict:
    """Convert a level-0 ROI to normalized [0,1] coords for frontend overlays."""
    return {
        "roi_id": roi.roi_id,
        "x": roi.x / slide_width if slide_width > 0 else 0.0,
        "y": roi.y / slide_height if slide_height > 0 else 0.0,
        "w": roi.width / slide_width if slide_width > 0 else 0.0,
        "h": roi.height / slide_height if slide_height > 0 else 0.0,
        "tissue_fraction": roi.tissue_fraction,
    }
