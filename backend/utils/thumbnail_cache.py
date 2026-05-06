"""
Thumbnail cache for WSI slides.

Two-tier strategy:
1. If the WSI is on disk (resolved via `backend.wsi.loader._resolve_path`),
   we extract a real low-res thumbnail with OpenSlide.
2. Otherwise we render a deterministic synthetic tissue-like thumbnail using
   PIL, keyed by `slide_id`. This keeps the Volume 3D viewer functional even
   before the multi-GB WSIs land on the MI300X — and serves as a stable
   placeholder for hackathon demos.

Generated images are cached on disk under `/tmp/pathmind_thumbs`.
"""

from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter

CACHE_DIR = Path(os.getenv("PATHMIND_THUMB_CACHE", "/tmp/pathmind_thumbs"))


# Bump this when the synthetic generator changes so old cached JPEGs are
# transparently superseded without manual cleanup on the AMD box.
_CACHE_VERSION = "v2"


def get_thumbnail_path(slide_id: str, size: int) -> Path:
    """Stable on-disk path for a given slide_id + size pair."""
    safe = slide_id.replace("/", "_").replace("..", "_")
    return CACHE_DIR / f"{safe}_{size}_{_CACHE_VERSION}.jpg"


def _save_jpeg(image: Image.Image, dest: Path, quality: int = 82) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(dest, "JPEG", quality=quality, optimize=True)


def _real_thumbnail(wsi_path: Path, size: int, dest: Path) -> Path:
    """Extract a thumbnail from a real WSI via OpenSlide."""
    import openslide  # local import — keeps optional dep loose
    slide = openslide.OpenSlide(str(wsi_path))
    try:
        thumb = slide.get_thumbnail((size, size))
    finally:
        slide.close()
    _save_jpeg(thumb, dest)
    return dest


def _synthetic_thumbnail(slide_id: str, size: int, dest: Path) -> Path:
    """Neutral H&E-tinted placeholder used when the real WSI is not on disk.

    Deliberately featureless — no fake "lesions" or stromal foci — so that the
    Tile-Triage ROIs (which are computed on the real WSI, not on this image)
    are not visually mismatched against fictitious tissue features. A subtle
    diagonal "PREVIEW" wordmark makes it obvious this is not the real slide.
    """
    img = Image.new("RGB", (size, size), (244, 232, 230))  # pale paraffin/H&E pink

    # Faint vignette to break the flat fill without implying tissue structure.
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    cx, cy = size // 2, size // 2
    rad = int(size * 0.55)
    for i in range(18):
        a = int(8 * (1 - i / 18))
        r = rad + i * 8
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(180, 150, 150, a), width=2)
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    # Very faint grain so JPEG doesn't band.
    noise = Image.effect_noise((size, size), 6).convert("RGB")
    img = Image.blend(img, noise, 0.04)
    img = img.filter(ImageFilter.GaussianBlur(radius=0.6))

    # PREVIEW watermark — repeated diagonal text. Use default font (always present).
    wm = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    wm_draw = ImageDraw.Draw(wm)
    label = "PREVIEW · WSI NON CHARGEE"
    step = max(120, size // 6)
    for y in range(-size, size * 2, step):
        for x in range(-size, size * 2, step * 2):
            wm_draw.text((x, y), label, fill=(120, 80, 90, 38))
    wm = wm.rotate(-30, resample=Image.BICUBIC, expand=False)
    img = Image.alpha_composite(img.convert("RGBA"), wm).convert("RGB")

    _save_jpeg(img, dest)
    return dest


def ensure_thumbnail(slide_id: str, wsi_path: Optional[Path], size: int = 1024) -> Path:
    """Return the cached thumbnail path. Build it if missing.

    If `wsi_path` is None or unreadable, we fall back to a synthetic thumbnail.
    The returned path is always populated with a valid JPEG.
    """
    out = get_thumbnail_path(slide_id, size)
    if out.exists() and out.stat().st_size > 0:
        return out

    if wsi_path and wsi_path.exists() and wsi_path.is_file():
        try:
            return _real_thumbnail(wsi_path, size, out)
        except Exception:
            # Any OpenSlide failure → fallback to synthetic, never break the endpoint.
            pass

    return _synthetic_thumbnail(slide_id, size, out)


def thumbnail_bytes(slide_id: str, wsi_path: Optional[Path], size: int = 1024) -> bytes:
    """Convenience helper: ensure + read the JPEG bytes."""
    p = ensure_thumbnail(slide_id, wsi_path, size)
    return p.read_bytes()
