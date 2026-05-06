"""
Slides API — thumbnails and case metadata for the Volume 3D Viewer.

Two endpoints:
- GET /api/slide/{slide_id}/thumbnail   → JPEG (real WSI thumbnail or deterministic synthetic)
- GET /api/case/{case_id}/slides        → JSON metadata + ROIs per slide for the volume viewer

The slide_id is the file_name (or stem) of the WSI; case_id matches the
`case_id` field in `data/demo/tcga_demo_cases.json` (e.g. "tcga-TCGA-OL-A66K").
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

from backend.utils.thumbnail_cache import ensure_thumbnail
from backend.wsi.loader import _resolve_path

router = APIRouter(prefix="/api", tags=["slides"])

ROOT = Path(__file__).resolve().parents[2]
DEMO_CASES_PATH = ROOT / "data" / "demo" / "tcga_demo_cases.json"

# Default ROIs returned when the pipeline has not yet produced real ones for a
# given slide. They give the Volume 3D viewer something visible without forcing
# the user to wait for analysis to complete. Coordinates are normalised (0..1).
_DEFAULT_ROIS = [
    {"x": 0.32, "y": 0.18, "w": 0.06, "h": 0.06, "tissue": 0.91},
    {"x": 0.61, "y": 0.41, "w": 0.06, "h": 0.06, "tissue": 0.83},
    {"x": 0.27, "y": 0.66, "w": 0.06, "h": 0.06, "tissue": 0.78},
]


def _load_demo_cases() -> list[dict[str, Any]]:
    """Read the demo cases JSON. Returns an empty list if absent."""
    if not DEMO_CASES_PATH.exists():
        return []
    try:
        return json.loads(DEMO_CASES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _slide_id_from_path(slide_path: str) -> str:
    """Use the basename without extension as the slide id (URL-safe-ish)."""
    return Path(slide_path).stem


_SLIDES_ROOTS = [
    Path("/root/pathmind/data/slides"),
    Path("/home/ubuntu/pathmind/data/slides"),
    Path("/data/slides"),
]


def _any_local_svs_for_prefix(prefix: str) -> Optional[Path]:
    """Return any .svs on disk whose stem starts with `prefix` (TCGA case ID)."""
    if not prefix:
        return None
    for root in _SLIDES_ROOTS:
        if not root.exists():
            continue
        for cand in root.rglob("*.svs"):
            if cand.stem.startswith(prefix):
                return cand
    return None


def _find_slide_wsi(slide_id: str) -> Optional[Path]:
    """Map a slide_id back to its on-disk WSI path.

    Resolution order:
    1. Exact match in tcga_demo_cases.json + file present on disk
    2. Same-case fallback: any other slide of the same TCGA case that IS on disk
       (DX1 may be 3+ GB and skipped at download time, but TS1 is usually local)
    3. Cross-case fuzzy: any local .svs sharing the same TCGA patient prefix
    """
    matched_case: Optional[dict] = None
    for case in _load_demo_cases():
        slide_paths = case.get("slide_paths", [])
        slide_names = case.get("slide_names", [])
        for i, sp in enumerate(slide_paths):
            candidates = {_slide_id_from_path(sp)}
            if i < len(slide_names):
                name = slide_names[i]
                candidates.add(name)
                candidates.add(Path(name).stem)
            if slide_id in candidates:
                resolved = _resolve_path(sp)
                if resolved is not None:
                    return resolved
                matched_case = case
                break
        if matched_case is not None:
            break

    # Same-case fallback: try any other slide_path of this case that's on disk
    if matched_case is not None:
        for sp in matched_case.get("slide_paths", []):
            r = _resolve_path(sp)
            if r is not None:
                return r

    # Cross-case fuzzy by TCGA patient prefix (e.g. "TCGA-OL-A66K")
    prefix = "-".join(slide_id.split("-")[:3])
    return _any_local_svs_for_prefix(prefix)


@router.get("/slide/{slide_id}/thumbnail")
def get_thumbnail(slide_id: str, size: int = Query(1024, ge=256, le=2048)):
    """Serve a JPEG thumbnail for the given slide_id.

    Falls back to a deterministic synthetic image if the underlying WSI file
    is not present on disk (typical before MI300X cloud allocation).
    """
    wsi = _find_slide_wsi(slide_id)
    thumb_path = ensure_thumbnail(slide_id, wsi, size)
    return FileResponse(
        thumb_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/case/{case_id}/slides")
def get_case_slides(case_id: str):
    """Return per-slide metadata (id, name, thumbnail URL, ROIs) for a case."""
    cases = _load_demo_cases()
    case = next((c for c in cases if c.get("case_id") == case_id), None)
    if not case:
        raise HTTPException(status_code=404, detail=f"case not found: {case_id}")

    slides = []
    for i, sp in enumerate(case.get("slide_paths", [])):
        sid = _slide_id_from_path(sp)
        slides.append({
            "id": sid,
            "index": i,
            "name": case.get("slide_names", [""])[i] if i < len(case.get("slide_names", [])) else sp,
            "path": sp,
            "thumbnail_url": f"/api/slide/{sid}/thumbnail",
            "rois": _DEFAULT_ROIS,
        })
    return JSONResponse({"case_id": case_id, "slides": slides})
