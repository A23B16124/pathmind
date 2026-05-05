# Volume 3D Viewer — Design Spec

**Date** : 2026-05-05
**Auteurs** : Zakaria Barji, Sam
**Contexte** : PathMind, AMD AI Hackathon (deadline 2026-05-09)
**Statut** : Validé par le Boss, prêt pour planification d'implémentation

---

## 1. Objectif

Permettre au pathologiste de visualiser plusieurs lames d'un même cas dans un espace 3D interactif. Chaque lame est un plan parallèle dans le volume. L'utilisateur peut tourner autour, zoomer, traverser le volume plan par plan (façon scanner CT), et entrer dans une lame pour la voir en 2D.

**Bénéfice clinique** : visualiser la distribution spatiale d'une tumeur à travers plusieurs coupes d'un même cas, avec mise en évidence des régions cancer (heatmap basée sur Tile-Triage).

**Bénéfice démo** : différenciateur visuel fort pour le jury — sort du wrapper LLM classique, montre une intégration WSI native + foundation models.

---

## 2. Décisions de design (validées avec le Boss)

| # | Question | Choix |
|---|----------|-------|
| 1 | Type de "3D" | Stack de plans parallèles 2D dans un espace 3D, navigable |
| 2 | Données démo | Télécharger plus de lames via GDC API pour cas TCGA existants |
| 3 | Texture par plan | Thumbnail + overlay heatmap cancer semi-transparente |
| 4 | Position UI | Nouvel onglet "Volume 3D" dans `ClinicalPanel` |
| 5 | Couleur | Tinte par profondeur + tissu désaturé + heatmap saturée |
| 6 | Source heatmap | Coordonnées des patches Tile-Triage (déjà dans le state) |
| 7 | Interactions | Orbit + zoom + clic-focus + traversée scroll style CT |

---

## 3. Architecture

```
ClinicalPanel
└── onglet "Volume 3D" (visible si slides.length >= 2)
    └── VolumeViewer (react-three-fiber)
        ├── SlideStack
        │   ├── SlidePlane × N
        │   │   ├── thumbnail JPEG (canvas texture)
        │   │   └── ROI overlay (rectangles rouge Tile-Triage)
        │   └── depth tint (HSL gradient par index)
        ├── CameraControls (drei)
        │   ├── orbit (drag)
        │   ├── zoom (scroll lent)
        │   └── traversée CT (scroll rapide → walk-through)
        └── SlideIndicator HUD ("Lame N / total")
```

**Stack technique** :
- `@react-three/fiber` — renderer React pour Three.js
- `@react-three/drei` — helpers (CameraControls, Html, useTexture)
- `three` — moteur 3D
- Canvas 2D natif pour composer thumbnail + ROI overlay avant upload texture

**Lazy loading** : `dynamic(() => import('./VolumeViewer'), { ssr: false })` — le bundle r3f ne charge qu'à l'ouverture de l'onglet.

---

## 4. Backend

### 4.1 Endpoint thumbnail

```
GET /api/slide/{slide_id}/thumbnail?size=1024
```

- Lit le WSI via OpenSlide
- `slide.get_thumbnail((size, size))` → PIL Image
- Encode en JPEG qualité 80
- Cache fichier `/tmp/pathmind_thumbs/{slide_id}_{size}.jpg`
- Header `Cache-Control: max-age=3600`
- Réponse : `image/jpeg` bytes

### 4.2 Endpoint slides metadata

```
GET /api/case/{case_id}/slides
```

Réponse :
```json
{
  "case_id": "TCGA-OL-A66K",
  "slides": [
    {
      "id": "slide_001",
      "index": 0,
      "name": "TCGA-OL-A66K-01Z-00-DX1.svs",
      "thumbnail_url": "/api/slide/slide_001/thumbnail",
      "rois": [
        {"x": 0.32, "y": 0.18, "w": 0.05, "h": 0.05, "tissue": 0.91},
        {"x": 0.45, "y": 0.62, "w": 0.05, "h": 0.05, "tissue": 0.88}
      ]
    }
  ]
}
```

ROIs viennent du dernier output Tile-Triage stocké en mémoire/DB pour ce cas.

### 4.3 Acquisition lames TCGA supplémentaires

Étendre `scripts/fetch_tcga_cases.py` :
- Ajouter `--max-slides N` flag
- Pour chaque case_id, récupérer toutes les lames diagnostiques + frozen + IHC disponibles via GDC `/files` endpoint
- Cibler 6-10 lames par cas pour TCGA-OL-A66K et TCGA-2L-AAQJ

---

## 5. Composant frontend `VolumeViewer.tsx`

### 5.1 Props

```ts
interface VolumeViewerProps {
  slides: SlideMetadata[]
  caseId: string
}

interface SlideMetadata {
  id: string
  index: number
  name: string
  thumbnail_url: string
  rois: ROIOverlay[]
}
```

### 5.2 Pipeline de rendu par plan (CPU canvas)

```ts
async function buildSlideTexture(slide: SlideMetadata, depthFactor: number): Promise<THREE.CanvasTexture> {
  // 1. Charger thumbnail
  const img = await loadImage(slide.thumbnail_url)

  // 2. Canvas 1024×1024
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = 1024
  const ctx = canvas.getContext('2d')!

  // 3. Désaturer le tissu (luminance × 0.4 + couleur × 0.6)
  ctx.drawImage(img, 0, 0, 1024, 1024)
  const imageData = ctx.getImageData(0, 0, 1024, 1024)
  const d = imageData.data
  for (let i = 0; i < d.length; i += 4) {
    const r = d[i], g = d[i+1], b = d[i+2]
    const lum = 0.299*r + 0.587*g + 0.114*b
    d[i]   = lum*0.4 + r*0.6
    d[i+1] = lum*0.4 + g*0.6
    d[i+2] = lum*0.4 + b*0.6
  }
  ctx.putImageData(imageData, 0, 0)

  // 4. Dessiner ROIs en oxblood semi-transparent
  ctx.fillStyle = 'rgba(107, 29, 29, 0.55)'
  for (const roi of slide.rois) {
    ctx.fillRect(roi.x*1024, roi.y*1024, roi.w*1024, roi.h*1024)
  }

  // 5. Tinte profondeur (overlay HSL en mode "color")
  const hue = depthFactor * 240  // 0=rouge, 240=bleu
  ctx.fillStyle = `hsla(${hue}, 60%, 50%, 0.15)`
  ctx.globalCompositeOperation = 'color'
  ctx.fillRect(0, 0, 1024, 1024)

  return new THREE.CanvasTexture(canvas)
}
```

### 5.3 Géométrie du stack

- `slidePlaneSize = 4` (unités world-space)
- `gap = 0.3` entre plans
- Position lame `i` : `z = -(i - N/2) * gap`
- Plans face caméra par défaut

### 5.4 Modes de caméra

```ts
type CameraMode = 'orbit' | 'ct_traversal' | 'focus'

// orbit : OrbitControls drei standard
// ct_traversal : caméra contrainte sur axe Z, scroll = changement plan actif
// focus : caméra interpolée vers position face à un plan donné
```

Transition `orbit → ct_traversal` : déclenchée si caméra entre dans la bounding-box du stack ET scroll > seuil.
Transition `* → focus` : clic sur un plan.
Sortie focus : touche Échap ou clic en dehors.

### 5.5 HUD

Composant `<Html>` (drei) overlay :
```
Lame 3 / 8
TCGA-OL-A66K-01Z-00-DX3
2 ROIs cancer détectées
[Échap pour vue volume]
```

---

## 6. Couleurs (cohérent avec design system existant)

| Élément | Couleur | Variable CSS |
|---------|---------|--------------|
| Heatmap cancer | `rgba(107, 29, 29, 0.55)` | `--accent` |
| Tinte profondeur haut | `hsla(0, 60%, 50%, 0.15)` | rouge |
| Tinte profondeur bas | `hsla(240, 60%, 50%, 0.15)` | bleu |
| Tissu désaturé | luminance × 0.4 | — |
| Background scène 3D | `#1c1a16` | `--ink` |
| HUD texte | `#f4f1ea` | `--paper` |

---

## 7. Intégration `ClinicalPanel`

```tsx
// frontend/components/clinical/ClinicalPanel.tsx

const slideCount = report?.slides?.length ?? 0
const tabs: { key: TabKey; label: string }[] = [
  { key: "diagnostic", label: "Diagnostic" },
  { key: "debate", label: "Débat" },
  { key: "literature", label: "Littérature" },
  ...(slideCount >= 2 ? [{ key: "volume3d" as TabKey, label: "Volume 3D" }] : []),
]

// dans le body :
{tab === "volume3d" && (
  <Suspense fallback={<div>Chargement...</div>}>
    <VolumeViewer slides={...} caseId={...} />
  </Suspense>
)}
```

---

## 8. Risques et mitigations

| Risque | Probabilité | Impact | Mitigation |
|--------|-------------|--------|------------|
| Cas TCGA avec < 2 lames diagnostiques | Élevée | Bloque la démo | Onglet caché si 1 lame. Cibler cas riches en IHC. Backup : générer cas synthétique multi-lames |
| Thumbnails lents (WSI 3GB OpenSlide) | Moyenne | UX dégradée | Pré-générer au téléchargement. Cache fichier persistant |
| Scroll CT conflit avec scroll page | Moyenne | Frustration UX | `e.preventDefault()` uniquement si pointeur dans canvas + bounding-box check |
| Bundle r3f trop lourd | Faible | Build Next.js fail | `dynamic(import, { ssr: false })`. Bundle isolé |
| Animation saccadée | Faible | Perception bug | `THREE.MathUtils.lerp` dans `useFrame`, target FPS 60 |
| Scope 1.5 jour dépassé | Élevée | Pas livré à temps | Fallback : downgrade interaction Full → Standard (juste clic-focus, pas traversée scroll) |

---

## 9. Plan de timeline (3 jours hackathon)

**J1 (mercredi 6 mai)**
- Matin : endpoints backend `thumbnail` + `slides metadata`
- Matin : étendre `scripts/fetch_tcga_cases.py` avec `--max-slides`, télécharger lames supplémentaires
- Après-midi : composant `VolumeViewer` minimal (stack de plans, orbit only, sans heatmap)

**J2 (jeudi 7 mai)**
- Matin : pipeline canvas (thumbnail + désaturation + ROI overlay + tinte profondeur)
- Après-midi : caméra modes (orbit / ct_traversal / focus) + transitions
- Après-midi : HUD `<Html>` indicateur lame

**J3 (vendredi 8 mai, jour pitch)**
- Matin : tests sur vrais TCGA, polish animations, fix bugs
- Matin : intégration onglet ClinicalPanel + condition d'affichage
- Après-midi : code freeze, pitch + démo répétés

---

## 10. Critères de succès (definition of done)

1. Onglet "Volume 3D" visible quand cas a >= 2 lames
2. Stack de plans rendu, chaque plan = thumbnail + ROIs visibles
3. Drag = rotation orbit fluide
4. Scroll = zoom puis traversée CT plan par plan
5. Clic sur plan = caméra s'aligne face, on lit la lame en 2D
6. Échap = retour orbit
7. HUD affiche lame courante + total
8. Tinte par profondeur visible mais pas agressive
9. Pas de régression sur les autres onglets (Diagnostic / Débat / Littérature)
10. Bundle Next.js build OK, pas d'erreur SSR

---

## 11. Hors-scope (post-hackathon)

- Heatmap continue basée sur embeddings Virchow2/UNI2 (vs rectangles ROI)
- Annotation par le pathologiste directement dans le 3D
- Export du volume en GLB/USDZ (AR mobile)
- Synchronisation multi-utilisateurs (consult à distance)
- Comparaison cas vs cas (deux volumes côte à côte)

---

## 12. Références

- [react-three-fiber](https://docs.pmnd.rs/react-three-fiber/)
- [drei CameraControls](https://drei.docs.pmnd.rs/controls/camera-controls)
- [OpenSlide get_thumbnail](https://openslide.org/api/python/#openslide.OpenSlide.get_thumbnail)
- [GDC API files endpoint](https://docs.gdc.cancer.gov/API/Users_Guide/Search_and_Retrieval/)
