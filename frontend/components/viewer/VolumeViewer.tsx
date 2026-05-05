'use client'

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { CameraControls, Html } from '@react-three/drei'
import { CanvasTexture, MathUtils, Mesh, Vector3 } from 'three'

// ─── Types ──────────────────────────────────────────────────────────────

interface ROI {
  x: number
  y: number
  w: number
  h: number
  tissue?: number
}

export interface SlideData {
  id: string
  index: number
  name: string
  thumbnail_url?: string
  rois: ROI[]
}

interface CaseSlidesResponse {
  case_id: string
  slides: Array<{
    id: string
    index: number
    name: string
    path: string
    thumbnail_url: string
    rois: ROI[]
  }>
}

interface Props {
  /** Inline slide data — used when caller already has it (legacy path). */
  slides?: SlideData[]
  /** Case id to fetch from /api/case/{caseId}/slides. Wins over `slides`. */
  caseId?: string
  activeSlideIndex?: number
  onSlideClick?: (i: number) => void
}

// ─── Constants ──────────────────────────────────────────────────────────

const TEX_SIZE = 1024
const PLANE_W = 4
const PLANE_H = 3
const PLANE_GAP = 1.1
const DESATURATE = 0.55           // 0 = original, 1 = grayscale
const ROI_FILL = 'rgba(139, 26, 26, 0.55)'
const ROI_STROKE = 'rgba(139, 26, 26, 0.95)'
const DEPTH_TINT_OPACITY = 0.18

// ─── API ────────────────────────────────────────────────────────────────

async function fetchCaseSlides(caseId: string): Promise<SlideData[]> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? ''
  const res = await fetch(`${apiUrl}/api/case/${encodeURIComponent(caseId)}/slides`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const data: CaseSlidesResponse = await res.json()
  return data.slides.map((s) => ({
    id: s.id,
    index: s.index,
    name: s.name,
    thumbnail_url: `${apiUrl}${s.thumbnail_url}`,
    rois: s.rois ?? [],
  }))
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error(`failed to load ${url}`))
    img.src = url
  })
}

// ─── Texture pipeline ──────────────────────────────────────────────────

/**
 * Compose a 1024×1024 canvas: thumbnail → desaturate → ROI overlay → depth tint.
 *
 * Source can be a real HTMLImageElement (when `thumbnail_url` resolved) or null
 * (in which case we fall back to a stable procedural texture so the viewer
 * still renders something distinct per slide).
 */
function buildSlideCanvas(
  source: HTMLImageElement | null,
  slide: SlideData,
  total: number,
): HTMLCanvasElement {
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = TEX_SIZE
  const ctx = canvas.getContext('2d')!

  if (source) {
    ctx.drawImage(source, 0, 0, TEX_SIZE, TEX_SIZE)

    // Desaturate so cancer ROIs stand out — luminance × DESATURATE + colour × (1 - DESATURATE)
    const imageData = ctx.getImageData(0, 0, TEX_SIZE, TEX_SIZE)
    const d = imageData.data
    const k = DESATURATE
    for (let i = 0; i < d.length; i += 4) {
      const r = d[i], g = d[i + 1], b = d[i + 2]
      const lum = 0.299 * r + 0.587 * g + 0.114 * b
      d[i]     = lum * k + r * (1 - k)
      d[i + 1] = lum * k + g * (1 - k)
      d[i + 2] = lum * k + b * (1 - k)
    }
    ctx.putImageData(imageData, 0, 0)
  } else {
    // Procedural fallback — stable per slide id, mimics H&E tissue.
    ctx.fillStyle = 'hsl(25, 20%, 85%)'
    ctx.fillRect(0, 0, TEX_SIZE, TEX_SIZE)
    const grain = ctx.createImageData(TEX_SIZE, TEX_SIZE)
    let seed = 0
    for (let i = 0; i < slide.id.length; i++) seed = (seed * 31 + slide.id.charCodeAt(i)) | 0
    for (let i = 0; i < grain.data.length; i += 4) {
      seed = (seed * 1664525 + 1013904223) | 0
      const n = ((seed & 0xff) - 128) * 0.07
      grain.data[i]     = 217 + n
      grain.data[i + 1] = 200 + n
      grain.data[i + 2] = 188 + n
      grain.data[i + 3] = 32
    }
    ctx.putImageData(grain, 0, 0)
    const vignette = ctx.createRadialGradient(
      TEX_SIZE / 2, TEX_SIZE / 2, TEX_SIZE * 0.25,
      TEX_SIZE / 2, TEX_SIZE / 2, TEX_SIZE * 0.7,
    )
    vignette.addColorStop(0, 'rgba(0,0,0,0)')
    vignette.addColorStop(1, 'rgba(0,0,0,0.35)')
    ctx.fillStyle = vignette
    ctx.fillRect(0, 0, TEX_SIZE, TEX_SIZE)
  }

  // Cancer ROIs in oxblood
  ctx.fillStyle = ROI_FILL
  ctx.strokeStyle = ROI_STROKE
  ctx.lineWidth = 3
  for (const roi of slide.rois) {
    const rx = roi.x * TEX_SIZE
    const ry = roi.y * TEX_SIZE
    const rw = roi.w * TEX_SIZE
    const rh = roi.h * TEX_SIZE
    ctx.fillRect(rx, ry, rw, rh)
    ctx.strokeRect(rx, ry, rw, rh)
  }

  // ROI tissue % labels
  ctx.font = `${Math.round(TEX_SIZE * 0.022)}px ui-monospace, SFMono-Regular, monospace`
  ctx.fillStyle = '#ffffff'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  for (const roi of slide.rois) {
    if (roi.tissue == null) continue
    const cx = (roi.x + roi.w / 2) * TEX_SIZE
    const cy = (roi.y + roi.h / 2) * TEX_SIZE
    ctx.fillText(`T:${Math.round(roi.tissue * 100)}%`, cx, cy)
  }

  // Depth tint — HSL 0° (red, top) → 240° (blue, bottom)
  const t = total > 1 ? slide.index / (total - 1) : 0
  const hue = t * 240
  ctx.save()
  ctx.globalAlpha = DEPTH_TINT_OPACITY
  ctx.fillStyle = `hsl(${hue}, 60%, 50%)`
  ctx.fillRect(0, 0, TEX_SIZE, TEX_SIZE)
  ctx.restore()

  return canvas
}

async function buildSlideTexture(slide: SlideData, total: number): Promise<CanvasTexture> {
  let img: HTMLImageElement | null = null
  if (slide.thumbnail_url) {
    try {
      img = await loadImage(slide.thumbnail_url)
    } catch {
      img = null
    }
  }
  const canvas = buildSlideCanvas(img, slide, total)
  const tex = new CanvasTexture(canvas)
  tex.needsUpdate = true
  return tex
}

// ─── 3D plane ───────────────────────────────────────────────────────────

interface SlidePlaneProps {
  slide: SlideData
  total: number
  isActive: boolean
  onClick?: (i: number) => void
}

function SlidePlane({ slide, total, isActive, onClick }: SlidePlaneProps) {
  const meshRef = useRef<Mesh>(null)
  const [texture, setTexture] = useState<CanvasTexture | null>(null)

  useEffect(() => {
    let cancelled = false
    buildSlideTexture(slide, total).then((tex) => {
      if (cancelled) {
        tex.dispose()
        return
      }
      setTexture(tex)
    })
    return () => {
      cancelled = true
    }
  }, [slide, total])

  useEffect(() => () => texture?.dispose(), [texture])

  useFrame((_, delta) => {
    const m = meshRef.current
    if (!m) return
    const target = isActive ? 1.05 : 0.92
    const k = 1 - Math.exp(-delta * 9)
    m.scale.x += (target - m.scale.x) * k
    m.scale.y += (target - m.scale.y) * k
    m.scale.z += (target - m.scale.z) * k
  })

  const handleClick = useCallback(() => onClick?.(slide.index), [onClick, slide.index])

  // Stack on Z, slight Y staircase for depth perception when orbiting
  const z = -slide.index * PLANE_GAP
  const y = slide.index * -0.05

  if (!texture) {
    return (
      <mesh position={[0, y, z]} rotation={[-0.05, 0, 0]} onClick={handleClick}>
        <planeGeometry args={[PLANE_W, PLANE_H]} />
        <meshBasicMaterial color="#1a1610" transparent opacity={0.35} />
      </mesh>
    )
  }

  return (
    <mesh ref={meshRef} position={[0, y, z]} rotation={[-0.05, 0, 0]} onClick={handleClick}>
      <planeGeometry args={[PLANE_W, PLANE_H]} />
      <meshBasicMaterial map={texture} transparent opacity={isActive ? 1 : 0.86} />
    </mesh>
  )
}

// ─── Camera focus driver ─────────────────────────────────────────────────

/**
 * Smoothly nudge the camera toward the active slide when in CT/focus mode.
 * Orbit mode is left untouched so the user can rotate freely.
 */
function CameraDriver({
  activeIndex,
  total,
  mode,
}: {
  activeIndex: number
  total: number
  mode: 'orbit' | 'focus' | 'ct'
}) {
  const { camera } = useThree()

  useFrame((_, delta) => {
    if (mode === 'orbit') return
    const targetZ = -activeIndex * PLANE_GAP + 4.2
    const targetY = activeIndex * -0.05 + 0.6
    const k = 1 - Math.exp(-delta * 4.5)
    camera.position.x += (0 - camera.position.x) * k
    camera.position.y += (targetY - camera.position.y) * k
    camera.position.z += (targetZ - camera.position.z) * k
    camera.lookAt(new Vector3(0, activeIndex * -0.05, -activeIndex * PLANE_GAP))
  })

  return null
}

// ─── HUD ────────────────────────────────────────────────────────────────

function SlideHUD({
  current,
  total,
  name,
  rois,
  mode,
}: {
  current: number
  total: number
  name: string
  rois: number
  mode: string
}) {
  const hint =
    mode === 'orbit'
      ? 'Drag · rotation · Scroll · navigation lame'
      : mode === 'focus'
      ? 'Échap · retour à la vue volume'
      : 'Scroll · traversée plan par plan'

  return (
    <Html fullscreen style={{ pointerEvents: 'none' }} zIndexRange={[10, 0]}>
      <div
        style={{
          position: 'absolute',
          top: 14,
          left: 14,
          padding: '10px 14px',
          background: 'rgba(28, 26, 22, 0.85)',
          borderLeft: '2px solid #6b1d1d',
          fontFamily: 'ui-serif, "Newsreader", serif',
          color: '#f4f1ea',
          minWidth: 220,
        }}
      >
        <div style={{ fontSize: 14, lineHeight: 1.2 }}>
          Lame {current + 1} / {total}
        </div>
        <div
          style={{
            fontFamily: 'ui-monospace, SFMono-Regular, monospace',
            fontSize: 10,
            opacity: 0.78,
            marginTop: 4,
            wordBreak: 'break-all',
          }}
        >
          {name}
        </div>
        <div
          style={{
            fontFamily: 'ui-monospace, SFMono-Regular, monospace',
            fontSize: 10,
            opacity: 0.66,
            marginTop: 4,
          }}
        >
          {rois} ROI{rois > 1 ? 's' : ''} cancer · mode {mode}
        </div>
      </div>
      <div
        style={{
          position: 'absolute',
          bottom: 14,
          left: 0,
          right: 0,
          textAlign: 'center',
          fontFamily: 'ui-monospace, SFMono-Regular, monospace',
          fontSize: 11,
          color: '#807866',
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
        }}
      >
        {hint}
      </div>
    </Html>
  )
}

// ─── Main component ────────────────────────────────────────────────────

export default function VolumeViewer({
  slides: inlineSlides,
  caseId,
  activeSlideIndex = 0,
  onSlideClick,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [internalIndex, setInternalIndex] = useState(activeSlideIndex)
  const [mode, setMode] = useState<'orbit' | 'focus' | 'ct'>('orbit')
  const [fetchedSlides, setFetchedSlides] = useState<SlideData[] | null>(null)
  const [fetchError, setFetchError] = useState<string | null>(null)

  // Fetch from API when caseId is provided. Falls back to inlineSlides on error.
  useEffect(() => {
    if (!caseId) {
      setFetchedSlides(null)
      return
    }
    let cancelled = false
    fetchCaseSlides(caseId)
      .then((s) => {
        if (!cancelled) setFetchedSlides(s)
      })
      .catch((e) => {
        if (!cancelled) {
          setFetchError(String(e))
          setFetchedSlides(null)
        }
      })
    return () => {
      cancelled = true
    }
  }, [caseId])

  const slides: SlideData[] = useMemo(() => {
    if (fetchedSlides && fetchedSlides.length > 0) return fetchedSlides
    return inlineSlides ?? []
  }, [fetchedSlides, inlineSlides])

  useEffect(() => {
    setInternalIndex((i) => MathUtils.clamp(activeSlideIndex, 0, Math.max(0, slides.length - 1)))
  }, [activeSlideIndex, slides.length])

  const clampIndex = useCallback(
    (i: number) => MathUtils.clamp(i, 0, Math.max(0, slides.length - 1)),
    [slides.length],
  )

  const handleSlideClick = useCallback(
    (i: number) => {
      const next = clampIndex(i)
      setInternalIndex(next)
      setMode('focus')
      onSlideClick?.(next)
    },
    [clampIndex, onSlideClick],
  )

  // Scroll → CT traversal (smooth lerp toward next plane)
  useEffect(() => {
    const el = containerRef.current
    if (!el || slides.length === 0) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const dir = e.deltaY > 0 ? 1 : -1
      setInternalIndex((prev) => {
        const next = clampIndex(prev + dir)
        if (next !== prev) onSlideClick?.(next)
        return next
      })
      setMode((m) => (m === 'orbit' ? 'ct' : m))
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [clampIndex, onSlideClick, slides.length])

  // Esc → return to orbit
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMode('orbit')
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  if (caseId && !fetchedSlides && !fetchError && (!inlineSlides || inlineSlides.length === 0)) {
    return (
      <div
        style={{ width: '100%', height: '100%', background: '#05080F' }}
        className="flex items-center justify-center text-[var(--muted)] font-mono text-xs"
      >
        Chargement du volume…
      </div>
    )
  }

  if (slides.length === 0) {
    return (
      <div
        style={{ width: '100%', height: '100%', background: '#05080F' }}
        className="flex items-center justify-center text-[var(--muted)] font-mono text-xs px-6 text-center"
      >
        Pas de lames pour ce cas{fetchError ? ` — ${fetchError}` : '.'}
      </div>
    )
  }

  const active = slides[internalIndex]

  return (
    <div ref={containerRef} style={{ width: '100%', height: '100%', background: '#05080F' }}>
      <Canvas camera={{ position: [0, 1.2, 6], fov: 45 }} style={{ background: '#05080F' }}>
        <CameraControls makeDefault enabled={mode === 'orbit'} />
        <ambientLight intensity={0.85} />
        <directionalLight position={[6, 6, 6]} intensity={0.35} />
        {slides.map((slide) => (
          <SlidePlane
            key={slide.id}
            slide={slide}
            total={slides.length}
            isActive={slide.index === internalIndex}
            onClick={handleSlideClick}
          />
        ))}
        <CameraDriver activeIndex={internalIndex} total={slides.length} mode={mode} />
        {active && (
          <SlideHUD
            current={internalIndex}
            total={slides.length}
            name={active.name}
            rois={active.rois.length}
            mode={mode}
          />
        )}
      </Canvas>
    </div>
  )
}
