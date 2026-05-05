# Volume 3D Viewer — Implementation Plan

> **Pour les workers agentiques :** Ce plan utilise `superpowers:subagent-driven-development` ou `superpowers:executing-plans`. Étapes en checkbox `- [ ]` pour le suivi.

**Goal :** Visualiser plusieurs lames d'un cas WSI dans un espace 3D interactif (orbit + zoom + traversée scroll style CT + focus lame).

**Architecture :** Onglet "Volume 3D" dans `ClinicalPanel`. Composant React `VolumeViewer` basé sur `react-three-fiber`. 2 nouveaux endpoints FastAPI pour servir thumbnails + ROIs.

**Tech Stack :** Next.js 15, react-three-fiber, drei, three.js, FastAPI, OpenSlide, Pillow.

**Spec source :** `docs/superpowers/specs/2026-05-05-3d-stack-viewer-design.md`

---

## RÈGLE DE COLLABORATION — STAY IN YOUR LANE

Ce plan est exécuté à 2 : **Zakaria (ZAK)** et **Sam (SAM)**. Chaque tâche est marquée `[ZAK]` ou `[SAM]`. Les deux Jarvis lisent le même plan mais **n'exécutent que les tâches taggées avec leur préfixe**.

**Règles dures :**

1. **ZAK ne touche jamais** aux fichiers : `backend/main.py`, `backend/api/slides.py`, `backend/utils/thumbnail_cache.py`, `scripts/fetch_tcga_cases.py`, `data/demo/tcga_demo_cases.json`.
2. **SAM ne touche jamais** aux fichiers : `frontend/**/*` (tout le frontend), `package.json`, `pnpm-lock.yaml`.
3. **Fichier partagé `frontend/lib/types.ts`** : ZAK l'édite. SAM ne l'édite PAS.
4. **Branche dédiée par personne** : `zak/volume3d-frontend` et `sam/volume3d-backend`. Pas de commit cross-branch.
5. **Merge final** : ZAK fait l'intégration (Tâche I-1) APRÈS que SAM ait merge sa branche dans main.
6. **Mocks pendant le dev** : ZAK utilise un mock JSON local (Tâche Z-2) tant que les endpoints SAM ne sont pas dispo. ZAK **n'attend pas** SAM pour démarrer.
7. **Conflit potentiel** : si l'un des deux pense devoir toucher un fichier de l'autre, **STOP** et synchroniser dans le chat avant.

**Ordre d'exécution recommandé :**
- SAM démarre PART A (backend)
- ZAK démarre PART B (frontend) en parallèle, avec mocks
- SAM merge en main
- ZAK swap le mock pour le vrai fetch dans Tâche Z-7
- ZAK fait Tâche I-1 (intégration finale)

---

## Structure des fichiers

**Créés par SAM :**
- `backend/api/__init__.py`
- `backend/api/slides.py` — router FastAPI 2 endpoints
- `backend/utils/thumbnail_cache.py` — utility cache fichiers thumbnails
- `tests/backend/test_slides_api.py` — tests endpoints

**Modifiés par SAM :**
- `backend/main.py` — `app.include_router(slides_router)` (1 ligne)
- `scripts/fetch_tcga_cases.py` — ajout flag `--max-slides`

**Créés par ZAK :**
- `frontend/components/viewer/VolumeViewer.tsx` — composant principal
- `frontend/components/viewer/SlideStack.tsx` — stack de plans + caméra modes
- `frontend/components/viewer/SlidePlane.tsx` — plan unitaire
- `frontend/components/viewer/textureBuilder.ts` — pipeline canvas 2D pure
- `frontend/components/viewer/cameraModes.ts` — logique transitions caméra
- `frontend/components/viewer/VolumeHUD.tsx` — overlay HUD
- `frontend/lib/mock-slides.ts` — mock data pour dev
- `frontend/__tests__/textureBuilder.test.ts` — test pipeline canvas

**Modifiés par ZAK :**
- `frontend/lib/types.ts` — ajout `SlideMetadata`, `CaseSlidesResponse`
- `frontend/components/clinical/ClinicalPanel.tsx` — onglet Volume 3D (intégration finale)
- `frontend/package.json` — deps `@react-three/fiber`, `@react-three/drei`, `three`

---

# PART A — TÂCHES [SAM]

> Sam : tu fais TOUT ce qui est dans cette section. Tu ne touches RIEN dans PART B (frontend). Tu commit sur `sam/volume3d-backend` puis merge en main quand A-5 est validée.

## [SAM] Tâche A-1 : Setup branche

**Files:**
- N/A

- [ ] **Étape 1 : Créer la branche**

```bash
cd /home/ubuntu/pathmind
git checkout main
git pull origin main
git checkout -b sam/volume3d-backend
```

- [ ] **Étape 2 : Vérifier l'état du repo**

Run : `git status`
Expected : `nothing to commit, working tree clean`

---

## [SAM] Tâche A-2 : Thumbnail cache utility

**Files:**
- Create: `backend/utils/thumbnail_cache.py`
- Test: `tests/backend/test_thumbnail_cache.py`

- [ ] **Étape 1 : Écrire le test**

```python
# tests/backend/test_thumbnail_cache.py
import pytest
from pathlib import Path
from backend.utils.thumbnail_cache import get_thumbnail_path, ensure_thumbnail

def test_get_thumbnail_path_uses_slide_id_and_size(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.utils.thumbnail_cache.CACHE_DIR", tmp_path)
    p = get_thumbnail_path("slide_abc", 1024)
    assert p == tmp_path / "slide_abc_1024.jpg"

def test_ensure_thumbnail_creates_jpeg_from_wsi(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.utils.thumbnail_cache.CACHE_DIR", tmp_path)
    # Path d'un WSI test minimal présent dans le repo
    wsi = Path("data/demo/test_slide_small.tiff")
    if not wsi.exists():
        pytest.skip("test slide absent")
    out = ensure_thumbnail("test_id", wsi, 512)
    assert out.exists()
    assert out.stat().st_size > 0
```

- [ ] **Étape 2 : Lancer le test (échec attendu)**

Run : `cd /home/ubuntu/pathmind && pytest tests/backend/test_thumbnail_cache.py -v`
Expected : `ModuleNotFoundError: No module named 'backend.utils.thumbnail_cache'`

- [ ] **Étape 3 : Implémenter le module**

```python
# backend/utils/thumbnail_cache.py
"""
Thumbnail cache for WSI slides.

Generates a low-res JPEG from a WSI file via OpenSlide and caches it on disk.
Returned bytes are reused across requests via Cache-Control on the API layer.
"""
from __future__ import annotations
from pathlib import Path

import openslide
from PIL import Image

CACHE_DIR = Path("/tmp/pathmind_thumbs")


def get_thumbnail_path(slide_id: str, size: int) -> Path:
    """Path on disk for the cached thumbnail (does not guarantee it exists)."""
    return CACHE_DIR / f"{slide_id}_{size}.jpg"


def ensure_thumbnail(slide_id: str, wsi_path: Path, size: int = 1024) -> Path:
    """Generate the thumbnail if missing, return its path."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = get_thumbnail_path(slide_id, size)
    if out.exists() and out.stat().st_size > 0:
        return out
    slide = openslide.OpenSlide(str(wsi_path))
    try:
        thumb = slide.get_thumbnail((size, size))
        thumb.convert("RGB").save(out, "JPEG", quality=80, optimize=True)
    finally:
        slide.close()
    return out
```

- [ ] **Étape 4 : Lancer le test (succès attendu)**

Run : `cd /home/ubuntu/pathmind && pytest tests/backend/test_thumbnail_cache.py -v`
Expected : 2 tests PASS (le second skip si pas de WSI test).

- [ ] **Étape 5 : Commit**

```bash
git add backend/utils/thumbnail_cache.py tests/backend/test_thumbnail_cache.py
git commit -m "feat(backend): add WSI thumbnail cache utility"
```

---

## [SAM] Tâche A-3 : API endpoints (slides router)

**Files:**
- Create: `backend/api/__init__.py`
- Create: `backend/api/slides.py`
- Test: `tests/backend/test_slides_api.py`

- [ ] **Étape 1 : Créer `backend/api/__init__.py` (fichier vide)**

```bash
touch backend/api/__init__.py
```

- [ ] **Étape 2 : Écrire le test endpoint**

```python
# tests/backend/test_slides_api.py
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_get_case_slides_returns_list_with_rois():
    """Endpoint /api/case/{case_id}/slides retourne une liste de lames."""
    r = client.get("/api/case/TCGA-OL-A66K/slides")
    assert r.status_code in (200, 404)  # 404 acceptable si cas absent
    if r.status_code == 200:
        data = r.json()
        assert "slides" in data
        assert isinstance(data["slides"], list)


def test_get_thumbnail_returns_jpeg_or_404():
    r = client.get("/api/slide/unknown_slide_id/thumbnail")
    # Devrait être 404 pour un id inconnu
    assert r.status_code == 404
```

- [ ] **Étape 3 : Lancer le test (échec attendu)**

Run : `cd /home/ubuntu/pathmind && pytest tests/backend/test_slides_api.py -v`
Expected : 404 sur les deux endpoints OU `AssertionError` parce que le router n'est pas branché.

- [ ] **Étape 4 : Implémenter le router**

```python
# backend/api/slides.py
"""
Slides API — thumbnails and case metadata for the Volume 3D Viewer.

Two endpoints:
- GET /api/slide/{slide_id}/thumbnail  → JPEG bytes (1024px default)
- GET /api/case/{case_id}/slides       → JSON metadata + ROIs per slide
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

from backend.utils.thumbnail_cache import ensure_thumbnail

router = APIRouter(prefix="/api", tags=["slides"])

DEMO_CASES_PATH = Path("data/demo/tcga_demo_cases.json")


def _load_demo_cases() -> dict[str, Any]:
    if not DEMO_CASES_PATH.exists():
        return {}
    return json.loads(DEMO_CASES_PATH.read_text())


def _find_slide_path(slide_id: str) -> Path | None:
    cases = _load_demo_cases()
    for case in cases.get("cases", []):
        for s in case.get("slides", []):
            if s.get("id") == slide_id:
                return Path(s["path"])
    return None


@router.get("/slide/{slide_id}/thumbnail")
def get_thumbnail(slide_id: str, size: int = Query(1024, ge=256, le=2048)):
    wsi_path = _find_slide_path(slide_id)
    if not wsi_path or not wsi_path.exists():
        raise HTTPException(status_code=404, detail=f"slide not found: {slide_id}")
    thumb_path = ensure_thumbnail(slide_id, wsi_path, size)
    return FileResponse(
        thumb_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "max-age=3600"},
    )


@router.get("/case/{case_id}/slides")
def get_case_slides(case_id: str):
    cases = _load_demo_cases()
    case = next((c for c in cases.get("cases", []) if c.get("case_id") == case_id), None)
    if not case:
        raise HTTPException(status_code=404, detail=f"case not found: {case_id}")
    slides = []
    for i, s in enumerate(case.get("slides", [])):
        slides.append({
            "id": s["id"],
            "index": i,
            "name": s.get("name", f"slide_{i}"),
            "thumbnail_url": f"/api/slide/{s['id']}/thumbnail",
            "rois": s.get("rois", []),
        })
    return JSONResponse({"case_id": case_id, "slides": slides})
```

- [ ] **Étape 5 : Brancher le router dans `main.py`**

Modifie `backend/main.py` — ajouter UNIQUEMENT ces 2 lignes (ne touche rien d'autre dans main.py) :

```python
from backend.api.slides import router as slides_router
app.include_router(slides_router)
```

À placer après les autres `include_router` ou imports d'app, AVANT `if __name__ == "__main__"` s'il existe.

- [ ] **Étape 6 : Lancer les tests**

Run : `cd /home/ubuntu/pathmind && pytest tests/backend/test_slides_api.py -v`
Expected : 2 tests PASS.

- [ ] **Étape 7 : Smoke test live**

Run :
```bash
pm2 restart pathmind-backend  # ou: uvicorn backend.main:app --reload --port 8011
curl -s http://localhost:8011/api/case/TCGA-OL-A66K/slides | head
```
Expected : JSON `{"case_id": "TCGA-OL-A66K", "slides": [...]}` ou 404 si pas encore de slides téléchargées.

- [ ] **Étape 8 : Commit**

```bash
git add backend/api/__init__.py backend/api/slides.py backend/main.py tests/backend/test_slides_api.py
git commit -m "feat(backend): add /api/slide thumbnail + /api/case slides endpoints"
```

---

## [SAM] Tâche A-4 : Étendre `fetch_tcga_cases.py` avec `--max-slides`

**Files:**
- Modify: `scripts/fetch_tcga_cases.py`

- [ ] **Étape 1 : Lire le script actuel**

```bash
cat scripts/fetch_tcga_cases.py | head -80
```

Repérer la fonction qui interroge GDC (probablement `find_diagnostic_slide` ou équivalent).

- [ ] **Étape 2 : Ajouter une fonction `find_all_slides`**

À placer juste après `find_diagnostic_slide` :

```python
def find_all_slides(case_uuid: str, max_slides: int = 10) -> list[dict]:
    """Return up to `max_slides` slide files for a given TCGA case_uuid.
    Includes diagnostic + frozen + IHC slides when available.
    """
    import requests
    GDC_API = "https://api.gdc.cancer.gov"
    filters = {
        "op": "and",
        "content": [
            {"op": "in", "content": {"field": "cases.case_id", "value": [case_uuid]}},
            {"op": "in", "content": {"field": "data_format", "value": ["SVS"]}},
            {"op": "in", "content": {"field": "data_type", "value": [
                "Slide Image", "Diagnostic Slide", "Tissue Slide"
            ]}},
        ],
    }
    fields = "file_id,file_name,file_size,data_type,experimental_strategy"
    params = {
        "filters": filters,
        "fields": fields,
        "format": "JSON",
        "size": str(max_slides),
    }
    r = requests.post(f"{GDC_API}/files", json=params, timeout=30)
    r.raise_for_status()
    return r.json().get("data", {}).get("hits", [])
```

- [ ] **Étape 3 : Ajouter le flag CLI**

Dans le `argparse` du script, ajouter :

```python
parser.add_argument("--max-slides", type=int, default=1,
                    help="Number of slides per case to fetch (default: 1, diagnostic only)")
```

Et dans le main, remplacer l'appel single-slide par :

```python
if args.max_slides > 1:
    hits = find_all_slides(case_uuid, args.max_slides)
else:
    hits = [find_diagnostic_slide(args.project_id)]
```

- [ ] **Étape 4 : Test rapide**

Run : `python3 scripts/fetch_tcga_cases.py --case TCGA-OL-A66K --max-slides 6 --dry-run`
Expected : la liste de 6 lames (ou moins si moins disponibles) s'affiche sans téléchargement.

- [ ] **Étape 5 : Commit**

```bash
git add scripts/fetch_tcga_cases.py
git commit -m "feat(scripts): support --max-slides for multi-slide TCGA cases"
```

---

## [SAM] Tâche A-5 : Télécharger les lames sur MI300X (à exécuter quand crédits AMD dispo)

**Files:**
- Modify: `data/demo/tcga_demo_cases.json` (regénéré par le script)

- [ ] **Étape 1 : Connecter à la VM MI300X et cloner le repo**

```bash
ssh mi300x  # ou IP/credentials AMD
git clone https://github.com/A23B16124/pathmind.git
cd pathmind
git checkout sam/volume3d-backend
```

- [ ] **Étape 2 : Télécharger 6-10 lames par cas TCGA**

```bash
python3 scripts/fetch_tcga_cases.py --case TCGA-OL-A66K --max-slides 8 --download
python3 scripts/fetch_tcga_cases.py --case TCGA-2L-AAQJ --max-slides 8 --download
```

Espace disque attendu : ~6 GB par cas (~12 GB total).

- [ ] **Étape 3 : Vérifier que `tcga_demo_cases.json` contient les nouvelles lames**

Run : `cat data/demo/tcga_demo_cases.json | jq '.cases[0].slides | length'`
Expected : `8` (ou le nombre réel téléchargé).

- [ ] **Étape 4 : Smoke test endpoints sur MI300X**

```bash
curl -s http://localhost:8011/api/case/TCGA-OL-A66K/slides | jq '.slides | length'
curl -s -o /tmp/thumb.jpg http://localhost:8011/api/slide/<un_slide_id>/thumbnail
file /tmp/thumb.jpg  # doit afficher: JPEG image data
```

- [ ] **Étape 5 : Commit + push**

```bash
git add data/demo/tcga_demo_cases.json
git commit -m "data: multi-slide TCGA cases (BRCA + PAAD)"
git push origin sam/volume3d-backend
```

- [ ] **Étape 6 : Merge en main**

```bash
git checkout main
git merge sam/volume3d-backend
git push origin main
```

Notifier ZAK dans le chat : "backend volume3d merged en main".

---

# PART B — TÂCHES [ZAK]

> Zakaria : tu fais TOUT ce qui est dans cette section. Tu ne touches RIEN dans PART A (backend). Tu commit sur `zak/volume3d-frontend`. Tu peux travailler en parallèle de SAM grâce aux mocks (Tâche Z-2). Tu remplaces le mock par le vrai fetch dans Z-7.

## [ZAK] Tâche Z-1 : Setup branche + dépendances

**Files:**
- Modify: `frontend/package.json`

- [ ] **Étape 1 : Créer la branche**

```bash
cd /home/ubuntu/pathmind
git checkout main
git pull origin main
git checkout -b zak/volume3d-frontend
```

- [ ] **Étape 2 : Installer les dépendances**

```bash
cd frontend
pnpm add three @react-three/fiber @react-three/drei
pnpm add -D @types/three
```

- [ ] **Étape 3 : Vérifier le build Next.js**

Run : `pnpm build`
Expected : build OK sans erreur.

- [ ] **Étape 4 : Commit**

```bash
git add frontend/package.json frontend/pnpm-lock.yaml
git commit -m "chore(frontend): add three + react-three-fiber + drei"
```

---

## [ZAK] Tâche Z-2 : Types + mock data

**Files:**
- Modify: `frontend/lib/types.ts`
- Create: `frontend/lib/mock-slides.ts`

- [ ] **Étape 1 : Ajouter les types dans `frontend/lib/types.ts`**

À ajouter à la fin du fichier :

```ts
export interface SlideMetadata {
  id: string
  index: number
  name: string
  thumbnail_url: string
  rois: ROIOverlay[]
}

export interface CaseSlidesResponse {
  case_id: string
  slides: SlideMetadata[]
}
```

- [ ] **Étape 2 : Créer le mock**

```ts
// frontend/lib/mock-slides.ts
import { CaseSlidesResponse } from "./types"

/** Mock data used during frontend dev before SAM's backend endpoints land. */
export const MOCK_VOLUME_3D: CaseSlidesResponse = {
  case_id: "TCGA-OL-A66K",
  slides: Array.from({ length: 8 }, (_, i) => ({
    id: `mock_slide_${i}`,
    index: i,
    name: `TCGA-OL-A66K-DX${i + 1}`,
    // Placeholder thumbnail (Lorem Picsum) until backend serves real ones
    thumbnail_url: `https://picsum.photos/seed/slide${i}/1024/1024`,
    rois: [
      { x: 0.32 + i * 0.02, y: 0.18, w: 0.05, h: 0.05, tissue: 0.91 },
      { x: 0.45, y: 0.62 - i * 0.03, w: 0.05, h: 0.05, tissue: 0.88 },
    ],
  })),
}
```

- [ ] **Étape 3 : Commit**

```bash
git add frontend/lib/types.ts frontend/lib/mock-slides.ts
git commit -m "feat(frontend): add SlideMetadata types + mock data for volume3d"
```

---

## [ZAK] Tâche Z-3 : Texture builder (TDD)

**Files:**
- Create: `frontend/components/viewer/textureBuilder.ts`
- Test: `frontend/__tests__/textureBuilder.test.ts`

- [ ] **Étape 1 : Écrire le test**

```ts
// frontend/__tests__/textureBuilder.test.ts
import { describe, it, expect } from "vitest"
import { buildSlideCanvas, depthHueDegrees } from "@/components/viewer/textureBuilder"

describe("depthHueDegrees", () => {
  it("returns 0 (red) for the top slide", () => {
    expect(depthHueDegrees(0, 8)).toBe(0)
  })
  it("returns 240 (blue) for the bottom slide", () => {
    expect(depthHueDegrees(7, 8)).toBeCloseTo(240, 0)
  })
  it("returns midpoint for the middle slide", () => {
    expect(depthHueDegrees(4, 8)).toBeCloseTo(137, 0)
  })
})

describe("buildSlideCanvas", () => {
  it("paints ROI rectangles in oxblood", async () => {
    const img = document.createElement("canvas")
    img.width = img.height = 1024
    const canvas = await buildSlideCanvas(img, [
      { x: 0.5, y: 0.5, w: 0.05, h: 0.05 },
    ], 0, 8)
    const ctx = canvas.getContext("2d")!
    const px = ctx.getImageData(525, 525, 1, 1).data
    // Au centre du ROI rouge oxblood : R doit dominer
    expect(px[0]).toBeGreaterThan(px[1])
    expect(px[0]).toBeGreaterThan(px[2])
  })
})
```

- [ ] **Étape 2 : Lancer le test (échec attendu)**

Run : `cd frontend && pnpm test textureBuilder`
Expected : `Cannot find module '@/components/viewer/textureBuilder'`.

- [ ] **Étape 3 : Implémenter le module**

```ts
// frontend/components/viewer/textureBuilder.ts
import * as THREE from "three"
import { ROIOverlay } from "@/lib/types"

const SIZE = 1024
const OXBLOOD = "rgba(107, 29, 29, 0.55)"
const DEPTH_TINT_OPACITY = 0.15
const DESATURATE_LUM = 0.4

/** HSL hue (degrees) for a given depth index — 0=red top, 240=blue bottom. */
export function depthHueDegrees(index: number, total: number): number {
  if (total <= 1) return 0
  return (index / (total - 1)) * 240
}

/** Build a 1024×1024 canvas: desaturated thumbnail + ROI overlays + depth tint. */
export async function buildSlideCanvas(
  source: HTMLImageElement | HTMLCanvasElement,
  rois: ROIOverlay[],
  index: number,
  total: number,
): Promise<HTMLCanvasElement> {
  const canvas = document.createElement("canvas")
  canvas.width = canvas.height = SIZE
  const ctx = canvas.getContext("2d")!

  ctx.drawImage(source, 0, 0, SIZE, SIZE)

  // Desaturate tissue
  const imageData = ctx.getImageData(0, 0, SIZE, SIZE)
  const d = imageData.data
  for (let i = 0; i < d.length; i += 4) {
    const r = d[i], g = d[i + 1], b = d[i + 2]
    const lum = 0.299 * r + 0.587 * g + 0.114 * b
    d[i]     = lum * DESATURATE_LUM + r * (1 - DESATURATE_LUM)
    d[i + 1] = lum * DESATURATE_LUM + g * (1 - DESATURATE_LUM)
    d[i + 2] = lum * DESATURATE_LUM + b * (1 - DESATURATE_LUM)
  }
  ctx.putImageData(imageData, 0, 0)

  // Cancer ROIs in oxblood
  ctx.fillStyle = OXBLOOD
  for (const roi of rois) {
    ctx.fillRect(roi.x * SIZE, roi.y * SIZE, roi.w * SIZE, roi.h * SIZE)
  }

  // Depth tint (HSL)
  const hue = depthHueDegrees(index, total)
  ctx.fillStyle = `hsla(${hue}, 60%, 50%, ${DEPTH_TINT_OPACITY})`
  ctx.globalCompositeOperation = "color"
  ctx.fillRect(0, 0, SIZE, SIZE)
  ctx.globalCompositeOperation = "source-over"

  return canvas
}

/** Async helper: load <img> from URL. */
export function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.crossOrigin = "anonymous"
    img.onload = () => resolve(img)
    img.onerror = reject
    img.src = url
  })
}

/** Build a Three.js CanvasTexture from a slide URL + ROIs. */
export async function buildSlideTexture(
  url: string,
  rois: ROIOverlay[],
  index: number,
  total: number,
): Promise<THREE.CanvasTexture> {
  const img = await loadImage(url)
  const canvas = await buildSlideCanvas(img, rois, index, total)
  const tex = new THREE.CanvasTexture(canvas)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.needsUpdate = true
  return tex
}
```

- [ ] **Étape 4 : Lancer le test**

Run : `cd frontend && pnpm test textureBuilder`
Expected : tous les tests PASS.

- [ ] **Étape 5 : Commit**

```bash
git add frontend/components/viewer/textureBuilder.ts frontend/__tests__/textureBuilder.test.ts
git commit -m "feat(frontend): add textureBuilder for volume3d slide canvas"
```

---

## [ZAK] Tâche Z-4 : `SlidePlane` component

**Files:**
- Create: `frontend/components/viewer/SlidePlane.tsx`

- [ ] **Étape 1 : Créer le composant**

```tsx
// frontend/components/viewer/SlidePlane.tsx
"use client"
import { useEffect, useState } from "react"
import * as THREE from "three"
import { SlideMetadata } from "@/lib/types"
import { buildSlideTexture } from "./textureBuilder"

interface Props {
  slide: SlideMetadata
  total: number
  z: number
  size?: number
  onClick?: (slide: SlideMetadata) => void
}

const PLANE_SIZE = 4

export function SlidePlane({ slide, total, z, size = PLANE_SIZE, onClick }: Props) {
  const [texture, setTexture] = useState<THREE.CanvasTexture | null>(null)

  useEffect(() => {
    let cancelled = false
    buildSlideTexture(slide.thumbnail_url, slide.rois, slide.index, total).then((tex) => {
      if (!cancelled) setTexture(tex)
    })
    return () => {
      cancelled = true
      texture?.dispose()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slide.thumbnail_url, slide.index, total])

  if (!texture) return null

  return (
    <mesh
      position={[0, 0, z]}
      onClick={(e) => { e.stopPropagation(); onClick?.(slide) }}
    >
      <planeGeometry args={[size, size]} />
      <meshBasicMaterial
        map={texture}
        transparent
        opacity={0.92}
        side={THREE.DoubleSide}
      />
    </mesh>
  )
}
```

- [ ] **Étape 2 : Commit**

```bash
git add frontend/components/viewer/SlidePlane.tsx
git commit -m "feat(frontend): add SlidePlane component"
```

---

## [ZAK] Tâche Z-5 : `SlideStack` + caméra modes

**Files:**
- Create: `frontend/components/viewer/cameraModes.ts`
- Create: `frontend/components/viewer/SlideStack.tsx`

- [ ] **Étape 1 : Créer `cameraModes.ts`**

```ts
// frontend/components/viewer/cameraModes.ts
import * as THREE from "three"

export type CameraMode = "orbit" | "ct_traversal" | "focus"

export const PLANE_GAP = 0.3
export const STACK_HALF_DEPTH = (count: number) => ((count - 1) * PLANE_GAP) / 2

/** Z position of the slide at a given index (centered around 0). */
export function planeZ(index: number, total: number): number {
  return -(index - (total - 1) / 2) * PLANE_GAP
}

/** Smoothly interpolate camera position toward a target. */
export function lerpCamera(
  camera: THREE.Camera,
  target: THREE.Vector3,
  alpha = 0.12,
): void {
  camera.position.lerp(target, alpha)
}

/** Camera target for "focus on slide N" — perpendicular to the plane. */
export function focusTarget(index: number, total: number): THREE.Vector3 {
  return new THREE.Vector3(0, 0, planeZ(index, total) + 2.4)
}
```

- [ ] **Étape 2 : Créer `SlideStack.tsx`**

```tsx
// frontend/components/viewer/SlideStack.tsx
"use client"
import { useEffect, useRef, useState } from "react"
import { useFrame, useThree } from "@react-three/fiber"
import { CameraControls } from "@react-three/drei"
import * as THREE from "three"
import { SlideMetadata } from "@/lib/types"
import { SlidePlane } from "./SlidePlane"
import { CameraMode, focusTarget, lerpCamera, planeZ } from "./cameraModes"

interface Props {
  slides: SlideMetadata[]
  onActiveChange?: (index: number) => void
  onModeChange?: (mode: CameraMode) => void
}

export function SlideStack({ slides, onActiveChange, onModeChange }: Props) {
  const total = slides.length
  const [mode, setMode] = useState<CameraMode>("orbit")
  const [activeIndex, setActiveIndex] = useState(0)
  const [focusIndex, setFocusIndex] = useState<number | null>(null)
  const controlsRef = useRef<CameraControls>(null!)
  const { camera } = useThree()

  useEffect(() => onModeChange?.(mode), [mode, onModeChange])
  useEffect(() => onActiveChange?.(activeIndex), [activeIndex, onActiveChange])

  // Keyboard: Escape exits focus
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && mode === "focus") {
        setMode("orbit")
        setFocusIndex(null)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [mode])

  // Wheel: zoom in/out, then CT traversal when inside the stack
  useEffect(() => {
    const onWheel = (e: WheelEvent) => {
      const inside = camera.position.distanceTo(new THREE.Vector3()) < 5
      if (mode === "orbit" && inside && Math.abs(e.deltaY) > 30) {
        setMode("ct_traversal")
      }
      if (mode === "ct_traversal") {
        e.preventDefault()
        const dir = e.deltaY > 0 ? 1 : -1
        setActiveIndex((i) => Math.max(0, Math.min(total - 1, i + dir)))
      }
    }
    const canvas = document.querySelector("canvas")
    canvas?.addEventListener("wheel", onWheel, { passive: false })
    return () => canvas?.removeEventListener("wheel", onWheel)
  }, [mode, camera, total])

  // Focus animation
  useFrame(() => {
    if (mode === "focus" && focusIndex !== null) {
      lerpCamera(camera, focusTarget(focusIndex, total))
    }
    if (mode === "ct_traversal") {
      const target = new THREE.Vector3(0, 0, planeZ(activeIndex, total) + 2.4)
      lerpCamera(camera, target, 0.18)
    }
  })

  const handlePlaneClick = (slide: SlideMetadata) => {
    setMode("focus")
    setFocusIndex(slide.index)
    setActiveIndex(slide.index)
  }

  return (
    <>
      <CameraControls ref={controlsRef} enabled={mode === "orbit"} />
      <ambientLight intensity={0.9} />
      <directionalLight position={[5, 5, 5]} intensity={0.4} />
      {slides.map((s) => (
        <SlidePlane
          key={s.id}
          slide={s}
          total={total}
          z={planeZ(s.index, total)}
          onClick={handlePlaneClick}
        />
      ))}
    </>
  )
}
```

- [ ] **Étape 3 : Commit**

```bash
git add frontend/components/viewer/cameraModes.ts frontend/components/viewer/SlideStack.tsx
git commit -m "feat(frontend): add SlideStack with orbit/CT/focus camera modes"
```

---

## [ZAK] Tâche Z-6 : `VolumeHUD` + `VolumeViewer`

**Files:**
- Create: `frontend/components/viewer/VolumeHUD.tsx`
- Create: `frontend/components/viewer/VolumeViewer.tsx`

- [ ] **Étape 1 : Créer `VolumeHUD.tsx`**

```tsx
// frontend/components/viewer/VolumeHUD.tsx
"use client"
import { SlideMetadata } from "@/lib/types"
import { CameraMode } from "./cameraModes"

interface Props {
  slides: SlideMetadata[]
  activeIndex: number
  mode: CameraMode
}

export function VolumeHUD({ slides, activeIndex, mode }: Props) {
  const slide = slides[activeIndex]
  if (!slide) return null
  return (
    <div className="absolute top-3 left-3 px-3 py-2 bg-[var(--ink)]/85 text-[var(--paper)] font-mono text-[11px] border-l-2 border-[var(--accent)]">
      <div className="font-serif text-[13px]">Lame {activeIndex + 1} / {slides.length}</div>
      <div className="text-[10px] opacity-80 mt-0.5">{slide.name}</div>
      <div className="text-[10px] opacity-60 mt-0.5">
        {slide.rois.length} ROI{slide.rois.length > 1 ? "s" : ""} cancer
      </div>
      <div className="text-[9.5px] opacity-50 mt-1.5 uppercase tracking-wider">
        {mode === "orbit" && "Drag · rotation · scroll : zoom"}
        {mode === "ct_traversal" && "Scroll : traversée plan par plan"}
        {mode === "focus" && "Échap : retour volume"}
      </div>
    </div>
  )
}
```

- [ ] **Étape 2 : Créer `VolumeViewer.tsx`**

```tsx
// frontend/components/viewer/VolumeViewer.tsx
"use client"
import { useEffect, useState } from "react"
import { Canvas } from "@react-three/fiber"
import { CaseSlidesResponse, SlideMetadata } from "@/lib/types"
import { SlideStack } from "./SlideStack"
import { VolumeHUD } from "./VolumeHUD"
import { CameraMode } from "./cameraModes"
import { MOCK_VOLUME_3D } from "@/lib/mock-slides"

interface Props {
  caseId?: string
  /** When true, ignore caseId and use the local mock instead. */
  useMock?: boolean
}

export function VolumeViewer({ caseId, useMock = false }: Props) {
  const [slides, setSlides] = useState<SlideMetadata[] | null>(null)
  const [activeIndex, setActiveIndex] = useState(0)
  const [mode, setMode] = useState<CameraMode>("orbit")
  const [error, setError] = useState<string | null>(null)
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? ""

  useEffect(() => {
    if (useMock || !caseId) {
      setSlides(MOCK_VOLUME_3D.slides)
      return
    }
    fetch(`${apiUrl}/api/case/${encodeURIComponent(caseId)}/slides`)
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const data: CaseSlidesResponse = await r.json()
        setSlides(data.slides)
      })
      .catch((e) => setError(String(e)))
  }, [caseId, useMock, apiUrl])

  if (error) return <div className="p-6 text-[var(--accent)]">Erreur chargement volume : {error}</div>
  if (!slides) return <div className="p-6 text-[var(--muted)]">Chargement du volume…</div>
  if (slides.length < 2) return <div className="p-6 text-[var(--muted)]">Pas assez de lames pour la vue 3D.</div>

  return (
    <div className="relative w-full h-full bg-[var(--ink)]">
      <Canvas camera={{ position: [0, 0, 6], fov: 45 }}>
        <SlideStack
          slides={slides}
          onActiveChange={setActiveIndex}
          onModeChange={setMode}
        />
      </Canvas>
      <VolumeHUD slides={slides} activeIndex={activeIndex} mode={mode} />
    </div>
  )
}
```

- [ ] **Étape 3 : Tester en isolation (route temporaire)**

Créer une page de test rapide :

```bash
mkdir -p frontend/app/dev/volume3d
cat > frontend/app/dev/volume3d/page.tsx <<'EOF'
"use client"
import dynamic from "next/dynamic"
const VolumeViewer = dynamic(() => import("@/components/viewer/VolumeViewer").then(m => m.VolumeViewer), { ssr: false })
export default function Page() {
  return <div className="w-screen h-screen"><VolumeViewer useMock /></div>
}
EOF
```

Run : `pnpm dev` puis ouvrir `http://localhost:3030/dev/volume3d`.
Expected : on voit 8 plans empilés, on peut tourner autour, scroll = zoom + traversée.

- [ ] **Étape 4 : Commit**

```bash
git add frontend/components/viewer/VolumeHUD.tsx frontend/components/viewer/VolumeViewer.tsx frontend/app/dev/volume3d/page.tsx
git commit -m "feat(frontend): add VolumeViewer + HUD with mock data, test route /dev/volume3d"
```

---

## [ZAK] Tâche Z-7 : Swap mock pour vrai fetch (après merge SAM)

**Files:**
- Modify: `frontend/components/viewer/VolumeViewer.tsx` (si besoin)

> **Prérequis :** Sam a annoncé "backend volume3d merged en main".

- [ ] **Étape 1 : Pull main + rebase**

```bash
cd /home/ubuntu/pathmind
git fetch origin
git checkout zak/volume3d-frontend
git rebase origin/main
```

- [ ] **Étape 2 : Tester avec un vrai cas**

Run :
```bash
curl -s http://localhost:8011/api/case/TCGA-OL-A66K/slides | jq '.slides | length'
```
Expected : > 1.

Ouvrir `http://localhost:3030/dev/volume3d?case=TCGA-OL-A66K` (ajouter param URL si nécessaire dans la page de test) ou modifier la page de test pour passer `caseId="TCGA-OL-A66K"` sans `useMock`.

Vérifier : on voit les vraies lames, les ROIs sont dessinées au bon endroit.

- [ ] **Étape 3 : Commit (si modifs)**

```bash
git add frontend/app/dev/volume3d/page.tsx
git commit -m "test(frontend): switch volume3d dev page to real backend"
```

---

# PART C — INTÉGRATION FINALE [ZAK]

> ZAK uniquement, après que les Tâches A-5 et Z-7 soient terminées.

## [ZAK] Tâche I-1 : Onglet Volume 3D dans `ClinicalPanel`

**Files:**
- Modify: `frontend/components/clinical/ClinicalPanel.tsx`

- [ ] **Étape 1 : Lire le fichier actuel**

Ouvrir `frontend/components/clinical/ClinicalPanel.tsx` pour repérer où sont définis `tabs` et le rendu conditionnel par tab.

- [ ] **Étape 2 : Étendre le type `TabKey`**

Remplacer :
```ts
type TabKey = "diagnostic" | "debate" | "literature"
```
par :
```ts
type TabKey = "diagnostic" | "debate" | "literature" | "volume3d"
```

- [ ] **Étape 3 : Ajouter l'onglet conditionnellement**

Dans la liste `tabs`, ajouter conditionnellement :

```tsx
const slideCount = report?.slides?.length ?? 0

const tabs: { key: TabKey; label: string }[] = [
  { key: "diagnostic", label: "Diagnostic" },
  { key: "debate", label: "Débat" },
  { key: "literature", label: "Littérature" },
  ...(slideCount >= 2 ? [{ key: "volume3d" as TabKey, label: "Volume 3D" }] : []),
]
```

- [ ] **Étape 4 : Importer dynamiquement le viewer**

En haut du fichier (après les autres imports) :

```tsx
import dynamic from "next/dynamic"
const VolumeViewer = dynamic(
  () => import("@/components/viewer/VolumeViewer").then((m) => m.VolumeViewer),
  { ssr: false, loading: () => <div className="p-6 text-[var(--muted)]">Chargement du volume…</div> },
)
```

- [ ] **Étape 5 : Brancher le rendu**

Dans la zone du body où sont rendus les tabs, ajouter :

```tsx
{tab === "volume3d" && (
  <VolumeViewer caseId={(report as any)?.case_id ?? (report as any)?.id} />
)}
```

(Si le `case_id` est disponible sous un autre nom dans `Report`, ajuster — sinon ajouter `case_id?: string` dans `Report` côté `frontend/lib/types.ts`.)

- [ ] **Étape 6 : Test manuel intégré**

Run :
```bash
pm2 restart pathmind-frontend
```
Ouvrir l'app, charger un cas TCGA avec >= 2 lames, vérifier que l'onglet "Volume 3D" apparaît, cliquer dessus, vérifier que le viewer affiche les vraies lames.

- [ ] **Étape 7 : Commit + merge**

```bash
git add frontend/components/clinical/ClinicalPanel.tsx
git commit -m "feat(frontend): integrate Volume 3D tab in ClinicalPanel"
git push origin zak/volume3d-frontend
git checkout main
git merge zak/volume3d-frontend
git push origin main
```

---

## [ZAK] Tâche I-2 : Cleanup route dev

**Files:**
- Delete: `frontend/app/dev/volume3d/page.tsx` (optionnel, peut rester pour debug)

- [ ] **Étape 1 : Si on veut nettoyer**

```bash
rm -rf frontend/app/dev/volume3d
git add -A
git commit -m "chore(frontend): remove volume3d dev route"
```

Sinon, garder pour debug en démo.

---

## [ZAK] Tâche I-3 : Test final pré-pitch

- [ ] **Étape 1 : Smoke test complet**

1. Charger un cas TCGA (TCGA-OL-A66K) dans l'app
2. Lancer le pipeline complet
3. Attendre la fin
4. Onglet "Volume 3D" doit apparaître
5. Cliquer dessus → 8 plans visibles
6. Drag → rotation OK
7. Scroll → zoom puis traversée CT
8. Clic sur un plan → caméra s'aligne
9. Échap → retour orbit
10. Pas de régression sur les autres onglets

- [ ] **Étape 2 : Si tout OK, tag**

```bash
git tag v-volume3d-ready
git push origin v-volume3d-ready
```

---

# Critères de succès globaux (Definition of Done)

- [ ] 2 endpoints backend OK et testés (SAM)
- [ ] Lames TCGA téléchargées et servies (SAM)
- [ ] Composant `VolumeViewer` rendu correctement avec mock (ZAK)
- [ ] 4 modes caméra fonctionnels : orbit, zoom, CT traversal, focus (ZAK)
- [ ] Tinte profondeur visible mais subtile (ZAK)
- [ ] ROIs cancer visibles en oxblood sur chaque plan (ZAK)
- [ ] HUD affiche lame courante (ZAK)
- [ ] Onglet Volume 3D dans ClinicalPanel, conditionnel (ZAK)
- [ ] Pas de régression sur les autres onglets (ZAK)
- [ ] Build Next.js OK (ZAK)
- [ ] Tests pytest et vitest passent

---

# Notes de risque

- **Si A-5 (téléchargement) prend > 1/2 journée** : SAM continue avec les lames qu'il a déjà obtenues, ZAK peut tester en mock. Pas de blocage.
- **Si Z-5 (caméra modes) déraille** : downgrade à orbit + clic-focus uniquement, abandonner CT traversal. Spec acknowledges that fallback (Section 8 du spec, ligne "downgrade interaction Full → Standard").
- **Si conflit Git inattendu sur `frontend/lib/types.ts`** : ZAK seul édite, SAM ne touche pas. Si problème, ZAK rebase et résout.
- **Si bundle r3f explose le build** : `dynamic({ ssr: false })` est en place, mais si vraiment problème, ZAK lazy-load le tab entier au clic plutôt qu'au chargement.
