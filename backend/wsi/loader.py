"""
WSI loader — OpenSlide wrapper for whole-slide images.

Supports .svs .ndpi .tiff .qptiff .mrxs.
Returns slide metadata + provides tile extraction at arbitrary coords/levels.

In MOCK_MODE the loader still works on real files, but agents may bypass it.
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import openslide
    from openslide import OpenSlide
    _OPENSLIDE_OK = True
except Exception:
    _OPENSLIDE_OK = False
    OpenSlide = None  # type: ignore


@dataclass
class SlideMeta:
    path: str
    width: int
    height: int
    level_count: int
    level_dimensions: list[tuple[int, int]] = field(default_factory=list)
    level_downsamples: list[float] = field(default_factory=list)
    mpp_x: Optional[float] = None
    mpp_y: Optional[float] = None
    objective_power: Optional[float] = None
    vendor: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "width": self.width,
            "height": self.height,
            "level_count": self.level_count,
            "level_dimensions": self.level_dimensions,
            "level_downsamples": self.level_downsamples,
            "mpp_x": self.mpp_x,
            "mpp_y": self.mpp_y,
            "objective_power": self.objective_power,
            "vendor": self.vendor,
        }


# Task 2: format whitelist + size guard
SUPPORTED_EXTENSIONS = {".svs", ".ndpi", ".tiff", ".tif", ".qptiff", ".mrxs", ".scn", ".vms", ".vmu"}
MAX_SLIDE_BYTES = int(os.getenv("MAX_SLIDE_BYTES", str(8 * 1024 ** 3)))  # 8 GB default
MIN_SLIDE_BYTES = 1024  # < 1 KB → almost certainly empty/corrupt


class WSILoadError(Exception):
    pass


def _validate_slide_path(resolved: Path) -> None:
    """Raise WSILoadError for unsupported extension or suspicious file size."""
    ext = resolved.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise WSILoadError(
            f"unsupported format '{ext}' — allowed: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    size = resolved.stat().st_size
    if size < MIN_SLIDE_BYTES:
        raise WSILoadError(f"slide file too small ({size} bytes) — likely empty or corrupt")
    if size > MAX_SLIDE_BYTES:
        raise WSILoadError(
            f"slide file too large ({size / 1024**3:.1f} GB) — max {MAX_SLIDE_BYTES / 1024**3:.0f} GB"
        )


_REPO_ROOT = Path(__file__).resolve().parents[2]


def _resolve_path(slide_path: str) -> Optional[Path]:
    """Resolve a slide path against common locations. Returns None if unfindable."""
    candidates = [
        Path(slide_path),
        _REPO_ROOT / "data" / "slides" / slide_path,
        Path("/home/ubuntu/pathmind/data/slides") / slide_path,
        Path(os.getenv("PATHMIND_SLIDES_DIR", "/data/slides")) / slide_path,
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return c
    return None


def open_slide(slide_path: str) -> SlideMeta:
    """Open a slide and return its metadata. Raises WSILoadError if file is missing or unreadable."""
    if not _OPENSLIDE_OK:
        raise WSILoadError("openslide not available — install libopenslide0 + openslide-python")

    resolved = _resolve_path(slide_path)
    if resolved is None:
        raise WSILoadError(f"slide not found: {slide_path}")

    _validate_slide_path(resolved)

    try:
        slide = OpenSlide(str(resolved))
    except WSILoadError:
        raise
    except Exception as e:
        raise WSILoadError(f"failed to open slide {resolved}: {e}") from e

    try:
        props = slide.properties
        mpp_x = _safe_float(props.get(openslide.PROPERTY_NAME_MPP_X))
        mpp_y = _safe_float(props.get(openslide.PROPERTY_NAME_MPP_Y))
        objective = _safe_float(props.get(openslide.PROPERTY_NAME_OBJECTIVE_POWER))
        vendor = props.get(openslide.PROPERTY_NAME_VENDOR)

        return SlideMeta(
            path=str(resolved),
            width=slide.dimensions[0],
            height=slide.dimensions[1],
            level_count=slide.level_count,
            level_dimensions=list(slide.level_dimensions),
            level_downsamples=list(slide.level_downsamples),
            mpp_x=mpp_x,
            mpp_y=mpp_y,
            objective_power=objective,
            vendor=vendor,
        )
    finally:
        slide.close()


def read_region_jpeg(
    slide_path: str,
    x: int,
    y: int,
    width: int,
    height: int,
    level: int = 0,
    quality: int = 85,
) -> bytes:
    """
    Read a rectangular region from the slide and return JPEG bytes.

    (x, y) are level-0 coordinates per OpenSlide convention.
    Output dims = (width, height) at the requested level.
    """
    if not _OPENSLIDE_OK:
        raise WSILoadError("openslide not available")

    resolved = _resolve_path(slide_path)
    if resolved is None:
        raise WSILoadError(f"slide not found: {slide_path}")

    slide = OpenSlide(str(resolved))
    try:
        if level >= slide.level_count:
            raise WSILoadError(f"level {level} out of range (max {slide.level_count - 1})")
        region = slide.read_region((x, y), level, (width, height)).convert("RGB")
        buf = io.BytesIO()
        region.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()
    finally:
        slide.close()


def thumbnail_jpeg(slide_path: str, max_size: int = 1024, quality: int = 80) -> bytes:
    """Return a JPEG thumbnail of the entire slide, longest side <= max_size."""
    if not _OPENSLIDE_OK:
        raise WSILoadError("openslide not available")
    resolved = _resolve_path(slide_path)
    if resolved is None:
        raise WSILoadError(f"slide not found: {slide_path}")

    slide = OpenSlide(str(resolved))
    try:
        thumb = slide.get_thumbnail((max_size, max_size)).convert("RGB")
        buf = io.BytesIO()
        thumb.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()
    finally:
        slide.close()


def _safe_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
