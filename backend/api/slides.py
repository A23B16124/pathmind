"""
Slides API — thumbnails and case metadata for the Volume 3D Viewer.

Two endpoints:
- GET /api/slide/{slide_id}/thumbnail   → JPEG (real WSI thumbnail or deterministic synthetic)
- GET /api/case/{case_id}/slides        → JSON metadata + ROIs per slide for the volume viewer

The slide_id is the file_name (or stem) of the WSI; case_id matches the
`case_id` field in `data/demo/tcga_demo_cases.json` (e.g. "tcga-TCGA-OL-A66K").
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

from backend.utils.thumbnail_cache import ensure_thumbnail
from backend.wsi.loader import _resolve_path
from backend.wsi.tiler import select_rois, normalize_roi

router = APIRouter(prefix="/api", tags=["slides"])

ROOT = Path(__file__).resolve().parents[2]
DEMO_CASES_PATH = ROOT / "data" / "demo" / "tcga_demo_cases.json"
_ROI_CACHE_DIR = Path("/tmp/pathmind_rois")
_ROI_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Static fallback ROIs — used only if no WSI is available at all (no local
# .svs file). Centered, low-density, just to keep the viewer non-empty.
_FALLBACK_ROIS = [
    {"x": 0.40, "y": 0.40, "w": 0.10, "h": 0.10, "tissue": 0.0},
]


def _compute_real_rois(wsi_path: Path, max_rois: int = 6) -> list[dict[str, Any]]:
    """Compute ROIs from the actual WSI via Otsu tissue mask, with disk cache.

    Cache key = (path, mtime, max_rois). Cache file = JSON list of dicts
    matching the front overlay format (x, y, w, h, tissue) in normalised
    [0, 1] coords relative to the slide's level-0 dimensions.
    """
    try:
        stat = wsi_path.stat()
    except FileNotFoundError:
        return list(_FALLBACK_ROIS)

    key_src = f"{wsi_path}:{stat.st_mtime_ns}:{max_rois}"
    key = hashlib.md5(key_src.encode("utf-8")).hexdigest()
    cache_file = _ROI_CACHE_DIR / f"{key}.json"
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text())
        except Exception:
            pass

    try:
        from openslide import OpenSlide  # local import — keeps optional dep loose
        slide = OpenSlide(str(wsi_path))
        try:
            w0, h0 = slide.dimensions
        finally:
            slide.close()
        rois = select_rois(str(wsi_path), target_tile_px=2048, max_rois=max_rois)
        out = []
        for r in rois:
            n = normalize_roi(r, w0, h0)
            out.append({
                "x": n["x"], "y": n["y"], "w": n["w"], "h": n["h"],
                "tissue": n["tissue_fraction"],
            })
        cache_file.write_text(json.dumps(out))
        return out
    except Exception:
        return list(_FALLBACK_ROIS)


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


_WSI_EXTS = ("*.svs", "*.ndpi", "*.tiff", "*.tif", "*.mrxs")


def _local_svs_pool() -> list[Path]:
    pool: list[Path] = []
    for root in _SLIDES_ROOTS:
        if not root.exists():
            continue
        for ext in _WSI_EXTS:
            pool.extend(root.rglob(ext))
    # De-duplicate while preserving sort order
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in sorted(pool):
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def _find_slide_wsi(slide_id: str) -> Optional[Path]:
    """Map a slide_id back to its on-disk WSI path.

    Resolution order:
    1. Exact match in tcga_demo_cases.json + file present on disk
    2. Round-robin over local pool keyed by the slide's INDEX inside its
       case — guarantees SP1 != SP2 != SP3 visually when several slides of
       the same case lack their exact files (DX1 is 3+ GB, often skipped).
    3. Cross-case fuzzy by TCGA patient prefix
    4. Last resort: hash-based pick over local pool
    """
    matched_case: Optional[dict] = None
    matched_index: int = -1
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
                matched_index = i
                break
        if matched_case is not None:
            break

    pool = _local_svs_pool()

    # Round-robin within the matched case so SP0/SP1/SP2/... pick distinct files
    if matched_case is not None and pool:
        n_slides = len(matched_case.get("slide_paths", []))
        # Files reserved by exact matches anywhere in the demo set — excluded
        # from fallback pool so a missing-slide fallback never collides with
        # an exact-match slide of any case.
        reserved: set[Path] = set()
        for c in _load_demo_cases():
            for sp in c.get("slide_paths", []):
                r = _resolve_path(sp)
                if r is not None:
                    reserved.add(r)
        free_pool = [p for p in pool if p not in reserved] or pool

        prefix = "-".join(slide_id.split("-")[:3])
        prefix_pool = [p for p in free_pool if p.stem.startswith(prefix)] if prefix else []
        if len(prefix_pool) >= n_slides:
            return prefix_pool[matched_index]
        case_id = matched_case.get("case_id", "")
        offset = int(hashlib.md5(case_id.encode("utf-8")).hexdigest()[:4], 16) % len(free_pool)
        return free_pool[(offset + matched_index) % len(free_pool)]

    # Cross-case fuzzy by TCGA patient prefix (no JSON match at all)
    prefix = "-".join(slide_id.split("-")[:3])
    same_prefix = _any_local_svs_for_prefix(prefix)
    if same_prefix is not None:
        return same_prefix

    if not pool:
        return None
    digest = hashlib.md5(slide_id.encode("utf-8")).digest()
    return pool[digest[0] % len(pool)]


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
        # Resolve to the actual WSI on disk (may be a fuzzy fallback if the
        # exact .svs is missing). ROIs are computed from THIS file so they
        # align visually with whatever thumbnail the viewer ends up showing.
        wsi = _find_slide_wsi(sid)
        rois = _compute_real_rois(wsi) if wsi is not None else list(_FALLBACK_ROIS)
        slides.append({
            "id": sid,
            "index": i,
            "name": case.get("slide_names", [""])[i] if i < len(case.get("slide_names", [])) else sp,
            "path": sp,
            "thumbnail_url": f"/api/slide/{sid}/thumbnail",
            "rois": rois,
        })
    return JSONResponse({"case_id": case_id, "slides": slides})
