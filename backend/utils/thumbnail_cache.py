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


def get_thumbnail_path(slide_id: str, size: int) -> Path:
    """Stable on-disk path for a given slide_id + size pair."""
    safe = slide_id.replace("/", "_").replace("..", "_")
    return CACHE_DIR / f"{safe}_{size}.jpg"


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
    """Generate a deterministic tissue-like thumbnail keyed by slide_id.

    The image looks like an H&E section: pinkish base, irregular tissue silhouette,
    darker stromal regions. Same `slide_id` always yields the same image — this
    matters because the frontend caches by URL and we want stability across reloads.
    """
    # Deterministic RNG seeded by slide_id
    seed = int(hashlib.sha1(slide_id.encode("utf-8")).hexdigest()[:8], 16)
    import random
    rng = random.Random(seed)

    img = Image.new("RGB", (size, size), (244, 235, 230))  # very pale pink — paraffin background
    draw = ImageDraw.Draw(img, "RGBA")

    # Soft tissue silhouette — irregular blob made of overlapping ellipses.
    cx, cy = size // 2, size // 2
    r0 = int(size * 0.30)
    pink = (220, 165, 175)
    for _ in range(18):
        ox = rng.randint(-int(size * 0.08), int(size * 0.08))
        oy = rng.randint(-int(size * 0.08), int(size * 0.08))
        rx = rng.randint(int(size * 0.20), int(size * 0.36))
        ry = rng.randint(int(size * 0.20), int(size * 0.36))
        draw.ellipse(
            [cx + ox - rx, cy + oy - ry, cx + ox + rx, cy + oy + ry],
            fill=pink + (180,),
        )

    # Darker stromal foci — a few small purple-ish regions to mimic dense cellularity.
    purple = (120, 60, 110)
    for _ in range(rng.randint(4, 8)):
        x = rng.randint(int(size * 0.25), int(size * 0.75))
        y = rng.randint(int(size * 0.25), int(size * 0.75))
        r = rng.randint(int(size * 0.04), int(size * 0.10))
        draw.ellipse([x - r, y - r, x + r, y + r], fill=purple + (130,))

    # Subtle noise overlay — adds grain, prevents hard edges.
    noise = Image.effect_noise((size, size), 12).convert("RGB")
    img = Image.blend(img, noise, 0.06)
    img = img.filter(ImageFilter.GaussianBlur(radius=1.4))

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
