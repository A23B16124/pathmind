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

from PIL import Image, ImageDraw, ImageFilter, ImageFont

CACHE_DIR = Path(os.getenv("PATHMIND_THUMB_CACHE", "/tmp/pathmind_thumbs"))

# Bump this when the synthetic generator changes so old cached JPEGs are
# transparently superseded without manual cleanup on the AMD box.
_CACHE_VERSION = "v4"

# Local test slides — used as texture base for the synthetic placeholder so it
# looks like real histology rather than a plain colour fill.
_TEXTURE_CANDIDATES = [
    Path("/home/ubuntu/pathmind/data/slides/CMU-1-JP2K-33005.svs"),
    Path("/home/ubuntu/pathmind/data/slides/JP2K-33003-1.svs"),
    Path("/home/ubuntu/pathmind/data/slides/CMU-1-Small-Region.svs"),
]


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


def _texture_base(size: int) -> Optional[Image.Image]:
    """Try to load a crop from a local test WSI as the placeholder texture.

    Returns None if OpenSlide is unavailable or no test slide is found.
    The returned image is (size×size) RGB, already colour-normalised toward H&E.
    """
    try:
        import openslide  # noqa: F401 — optional dep
    except Exception:
        return None

    import openslide as osl

    for candidate in _TEXTURE_CANDIDATES:
        if not candidate.exists():
            continue
        try:
            slide = osl.OpenSlide(str(candidate))
            try:
                thumb = slide.get_thumbnail((size, size))
                thumb = thumb.convert("RGB").resize((size, size), Image.LANCZOS)
                # Shift colours toward H&E pink by blending with a tint layer.
                tint = Image.new("RGB", (size, size), (244, 220, 218))
                thumb = Image.blend(thumb, tint, 0.25)
                return thumb
            finally:
                slide.close()
        except Exception:
            continue
    return None


def _synthetic_thumbnail(slide_id: str, size: int, dest: Path) -> Path:
    """H&E-textured placeholder used when the real WSI is not on disk.

    Uses a local test-slide crop as the texture base (real tissue structure,
    wrong patient) so the image looks like genuine histology. The diagonal
    "PREVIEW" wordmark makes it unambiguous this is not the actual slide.
    """
    base = _texture_base(size)
    if base is None:
        base = Image.new("RGB", (size, size), (244, 232, 230))

    img = base

    # PREVIEW watermark — repeated diagonal text. Use DejaVu so accents render.
    wm = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    wm_draw = ImageDraw.Draw(wm)
    font_size = max(14, size // 44)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()
    label = "PREVIEW · WSI NON CHARGÉE"
    step = max(140, size // 5)
    for y in range(-size, size * 2, step):
        for x in range(-size, size * 2, step * 2):
            wm_draw.text((x, y), label, fill=(240, 240, 240, 110), font=font)
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
