'use client'
import { useEffect, useRef, useMemo } from 'react'
import OpenSeadragon from 'openseadragon'
import { ZoomIn, ZoomOut, Home } from 'lucide-react'

// Animated canvas: fixed neurons with phased fade in/out + ephemeral random
// links that connect nearby nodes for ~1.5s with a synapse pulse, then vanish.
// One requestAnimationFrame loop, no per-element CSS animation, no SVG filters.
function NeuralCanvas({ size }: { size: number }) {
  const ref = useRef<HTMLCanvasElement>(null)

  // Fixed positions (deterministic, computed once)
  const nodes = useMemo(() => {
    const list: { x: number; y: number; r: number; phase: number; speed: number }[] = []
    // inner ring (just outside the sphere)
    for (let i = 0; i < 14; i++) {
      const a = (i / 14) * Math.PI * 2 + 0.2
      const r = size * 0.62 + Math.sin(i * 2.3) * 10
      list.push({ x: Math.cos(a) * r, y: Math.sin(a) * r, r: 1.8, phase: i * 0.7, speed: 0.6 + (i % 3) * 0.18 })
    }
    // mid ring
    for (let i = 0; i < 18; i++) {
      const a = (i / 18) * Math.PI * 2 + 0.55
      const r = size * 0.92 + Math.sin(i * 1.7) * 26
      list.push({ x: Math.cos(a) * r, y: Math.sin(a) * r, r: 2.4, phase: i * 0.93 + 1.3, speed: 0.5 + (i % 4) * 0.15 })
    }
    // far stragglers
    for (let i = 0; i < 8; i++) {
      const a = (i / 8) * Math.PI * 2 + 1.1
      const r = size * 1.18 + Math.sin(i * 3.1) * 18
      list.push({ x: Math.cos(a) * r, y: Math.sin(a) * r, r: 3, phase: i * 1.4 + 2.2, speed: 0.35 + (i % 3) * 0.12 })
    }
    return list
  }, [size])

  // Pre-compute candidate edges (each node → 3 nearest neighbours within range)
  const candidates = useMemo(() => {
    const out: { i: number; j: number }[] = []
    const maxD = size * 0.45
    nodes.forEach((n, i) => {
      const others = nodes
        .map((m, j) => ({ j, d: Math.hypot(n.x - m.x, n.y - m.y) }))
        .filter((o) => o.j !== i && o.d > 18 && o.d < maxD)
        .sort((a, b) => a.d - b.d)
        .slice(0, 3)
      for (const { j } of others) {
        if (i < j) out.push({ i, j })
      }
    })
    return out
  }, [nodes, size])

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    const W = canvas.clientWidth
    const H = canvas.clientHeight
    canvas.width = W * dpr
    canvas.height = H * dpr
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    const cx = W / 2
    const cy = H / 2

    type ActiveLink = { i: number; j: number; born: number; life: number; speed: number }
    const links: ActiveLink[] = []
    const MAX_LINKS = 5

    let raf = 0
    let last = performance.now()
    let nextSpawn = 0

    const tick = (now: number) => {
      const t = now / 1000
      const dt = Math.min(0.05, (now - last) / 1000)
      last = now

      // spawn a random link occasionally
      if (now > nextSpawn && links.length < MAX_LINKS && candidates.length > 0) {
        const pick = candidates[Math.floor(Math.random() * candidates.length)]
        // de-duplicate
        if (!links.some((l) => l.i === pick.i && l.j === pick.j)) {
          links.push({
            i: pick.i,
            j: pick.j,
            born: t,
            life: 1.4 + Math.random() * 1.2,
            speed: 0.7 + Math.random() * 0.7,
          })
        }
        nextSpawn = now + 250 + Math.random() * 500
      }

      ctx.clearRect(0, 0, W, H)

      // links — drawn under nodes
      for (let k = links.length - 1; k >= 0; k--) {
        const l = links[k]
        const age = t - l.born
        if (age >= l.life) { links.splice(k, 1); continue }
        const u = age / l.life
        // fade in/out: ease-in-out
        const fade = u < 0.2 ? u / 0.2 : u > 0.7 ? (1 - u) / 0.3 : 1
        const a = nodes[l.i]; const b = nodes[l.j]
        const ax = cx + a.x; const ay = cy + a.y
        const bx = cx + b.x; const by = cy + b.y

        // base line
        ctx.strokeStyle = `rgba(232,224,212,${0.25 * fade})`
        ctx.lineWidth = 0.8
        ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke()

        // synapse pulse — small bright dot travelling along the line
        const p = (age * l.speed) % 1
        const px = ax + (bx - ax) * p
        const py = ay + (by - ay) * p
        const grad = ctx.createRadialGradient(px, py, 0, px, py, 9)
        grad.addColorStop(0, `rgba(255,255,255,${0.95 * fade})`)
        grad.addColorStop(0.4, `rgba(232,224,212,${0.55 * fade})`)
        grad.addColorStop(1, 'rgba(232,224,212,0)')
        ctx.fillStyle = grad
        ctx.beginPath(); ctx.arc(px, py, 9, 0, Math.PI * 2); ctx.fill()
      }

      // nodes
      for (const n of nodes) {
        const phase = Math.sin(t * n.speed + n.phase) * 0.5 + 0.5 // 0..1
        const op = 0.18 + 0.82 * Math.pow(phase, 1.6)
        const r = n.r * (0.6 + 0.7 * phase)
        const x = cx + n.x; const y = cy + n.y
        // glow
        const g = ctx.createRadialGradient(x, y, 0, x, y, r * 4)
        g.addColorStop(0, `rgba(255,255,255,${op * 0.9})`)
        g.addColorStop(0.4, `rgba(232,224,212,${op * 0.35})`)
        g.addColorStop(1, 'rgba(232,224,212,0)')
        ctx.fillStyle = g
        ctx.beginPath(); ctx.arc(x, y, r * 4, 0, Math.PI * 2); ctx.fill()
        // core
        ctx.fillStyle = `rgba(245,237,224,${op})`
        ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill()
      }

      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [nodes, candidates])

  return (
    <canvas
      ref={ref}
      width={size * 3}
      height={size * 3}
      className="absolute z-[5] pointer-events-none"
      style={{
        width: size * 3,
        height: size * 3,
        left: '50%',
        top: '50%',
        transform: 'translate(-50%, -50%)',
      }}
      aria-hidden="true"
    />
  )
}

function PathMindLogo() {
  // True CSS 3D wireframe sphere.
  // Meridians = circles tilted around Y axis. Parallels = circles flat (rotateX 90°)
  // translated up/down along Y. Whole .sphere container spins on Y + slight X tilt.
  const SIZE = 460
  const meridianAngles = Array.from({ length: 12 }, (_, i) => (i * 180) / 12)
  const parallels = [-60, -40, -20, 0, 20, 40, 60] // latitudes in degrees

  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center bg-[#09090d] overflow-hidden select-none">
      <style>{`
        @keyframes pm-spin    { from { transform: rotateX(-12deg) rotateY(0deg); } to { transform: rotateX(-12deg) rotateY(360deg); } }
        @keyframes pm-pulse   { 0%,100% { opacity: 0.92; } 50% { opacity: 1; } }
        @keyframes pm-node    { 0%,100% { transform: scale(0.6); opacity: 0.4; } 50% { transform: scale(1); opacity: 1; } }
        @keyframes pm-halo    { 0%,100% { opacity: 0.6; } 50% { opacity: 1; } }
        .pm-scene  { perspective: 1100px; perspective-origin: 50% 50%; }
        .pm-sphere { transform-style: preserve-3d; animation: pm-spin 16s linear infinite; }
        .pm-ring   { position: absolute; inset: 0; border: 1px solid rgba(232,224,212,0.55); border-radius: 50%; box-sizing: border-box; }
        .pm-ring-thin { border-width: 0.5px; opacity: 0.42; }
        .pm-ring-thick { border-width: 1.4px; opacity: 0.88; box-shadow: 0 0 16px rgba(232,224,212,0.35); }
        .pm-node   { position: absolute; width: 6px; height: 6px; left: 50%; top: 50%; margin: -3px 0 0 -3px; background: #f5ede0; border-radius: 50%; box-shadow: 0 0 8px #e8e0d4, 0 0 16px rgba(232,224,212,0.6); animation: pm-node 2.4s ease-in-out infinite; }
        .pm-pcap   { fill: #ffffff; font-family: ui-serif, Georgia, "Times New Roman", serif; font-style: italic; font-weight: 600; filter: drop-shadow(0 0 18px rgba(232,224,212,0.95)) drop-shadow(0 0 36px rgba(232,224,212,0.5)); animation: pm-pulse 3.6s ease-in-out infinite; }
      `}</style>

      {/* CRT scanlines */}
      <div
        className="pointer-events-none absolute inset-0 z-30"
        style={{
          backgroundImage: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.22) 2px, rgba(0,0,0,0.22) 4px)',
          mixBlendMode: 'multiply',
        }}
      />
      {/* Vignette */}
      <div
        className="pointer-events-none absolute inset-0 z-30"
        style={{ background: 'radial-gradient(ellipse at 50% 50%, transparent 45%, rgba(0,0,0,0.82) 100%)' }}
      />
      {/* Halo */}
      <div
        className="pointer-events-none absolute z-0"
        style={{
          width: SIZE * 1.6,
          height: SIZE * 1.6,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(232,224,212,0.14) 0%, rgba(232,224,212,0.05) 35%, transparent 65%)',
          filter: 'blur(22px)',
          animation: 'pm-halo 4s ease-in-out infinite',
        }}
      />

      {/* Neural canvas — fixed neurons fading in/out + ephemeral random links */}
      <NeuralCanvas size={SIZE} />

      {/* The 3D scene */}
      <div className="pm-scene relative z-10" style={{ width: SIZE, height: SIZE }}>
        <div className="pm-sphere absolute inset-0">
          {/* Meridians — full-size circles tilted around Y axis */}
          {meridianAngles.map((deg, i) => (
            <div
              key={`m-${i}`}
              className={`pm-ring ${deg === 0 ? 'pm-ring-thick' : 'pm-ring-thin'}`}
              style={{ transform: `rotateY(${deg}deg)` }}
            />
          ))}

          {/* Parallels — flat circles translated along Y, scaled by cos(lat) */}
          {parallels.map((lat) => {
            const r = (SIZE / 2) * Math.cos((lat * Math.PI) / 180)
            const yOffset = (SIZE / 2) * Math.sin((lat * Math.PI) / 180)
            const isEquator = lat === 0
            return (
              <div
                key={`p-${lat}`}
                className={`pm-ring ${isEquator ? 'pm-ring-thick' : 'pm-ring-thin'}`}
                style={{
                  width: r * 2,
                  height: r * 2,
                  left: '50%',
                  top: '50%',
                  marginLeft: -r,
                  marginTop: -r,
                  inset: 'auto',
                  transform: `translateY(${yOffset}px) rotateX(90deg)`,
                }}
              />
            )
          })}

          {/* Polar caps + a few orbiting nodes (positioned in 3D so they ride the rotation) */}
          <div className="pm-node" style={{ transform: `translateZ(${SIZE / 2}px)` }} />
          <div className="pm-node" style={{ transform: `translateZ(${-SIZE / 2}px)`, animationDelay: '0.8s' }} />
          <div className="pm-node" style={{ transform: `translateY(${-SIZE / 2}px) rotateX(90deg)`, animationDelay: '1.4s' }} />
          <div className="pm-node" style={{ transform: `translateY(${SIZE / 2}px) rotateX(90deg)`, animationDelay: '0.4s' }} />
          <div className="pm-node" style={{ transform: `rotateY(60deg) translateZ(${SIZE / 2}px)`, animationDelay: '1.1s' }} />
          <div className="pm-node" style={{ transform: `rotateY(-120deg) translateZ(${SIZE / 2}px)`, animationDelay: '1.7s' }} />
        </div>
      </div>

      {/* Central P — sits above sphere, doesn't rotate (always faces user) */}
      <svg
        className="absolute z-20 pointer-events-none"
        width={SIZE}
        height={SIZE}
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        style={{ top: '50%', left: '50%', transform: `translate(-50%, calc(-50% - 30px))` }}
        aria-hidden="true"
      >
        <text
          x={SIZE / 2}
          y={SIZE / 2 + 100}
          textAnchor="middle"
          className="pm-pcap"
          style={{ fontSize: '300px' }}
        >
          P
        </text>
      </svg>

      {/* Wordmark */}
      <div
        className="absolute z-20 pointer-events-none"
        style={{
          left: '50%',
          top: `calc(50% + ${SIZE / 2}px + 28px)`,
          transform: 'translateX(-50%)',
          textAlign: 'center',
        }}
      >
        <div
          className="font-mono uppercase text-[#f5ede0]"
          style={{
            fontSize: 18,
            letterSpacing: '0.42em',
            textShadow: '0 0 24px rgba(232,224,212,0.7)',
          }}
        >
          PATHMIND
        </div>
        <div
          className="font-mono mt-3 text-[#e8e0d4]"
          style={{ fontSize: 11, opacity: 0.5, letterSpacing: '0.18em' }}
        >
          Chargez une lame pour commencer l&apos;analyse
        </div>
      </div>
    </div>
  )
}

export interface Overlay {
  x: number
  y: number
  w: number
  h: number
  color?: string
  label?: string
}

const DEFAULT_OVERLAY_COLOR = "#3b82f6"

interface WSIViewerProps {
  slideId: string
  className?: string
  overlays?: Overlay[]
}

const PLACEHOLDER_TILE_SOURCE = 'https://openseadragon.github.io/example-images/highsmith/highsmith.dzi'
const API_BASE = process.env.NEXT_PUBLIC_API_URL || ''

// Build a single-image tileSource from a backend thumbnail. OpenSeadragon
// can pan/zoom a flat JPEG via the simpleImage type — good enough for the
// demo until we expose a real DZI/IIIF tile server backed by OpenSlide.
function buildTileSource(slideId: string): unknown {
  const isDemoLabel = !slideId || slideId === 'Aucune lame' || slideId === 'Pas de lame chargée'
  if (isDemoLabel || !API_BASE) return PLACEHOLDER_TILE_SOURCE
  const safeId = encodeURIComponent(slideId.replace(/\.svs$/i, ''))
  return {
    type: 'image',
    url: `${API_BASE}/api/slide/${safeId}/thumbnail?size=2048`,
    crossOriginPolicy: 'Anonymous',
  }
}

export function WSIViewer({ slideId, className, overlays }: WSIViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const viewerRef = useRef<OpenSeadragon.Viewer | null>(null)
  const isReadyRef = useRef(false)

  const isPlaceholder = !slideId || slideId === 'Aucune lame' || slideId === 'Pas de lame chargée'

  useEffect(() => {
    if (!containerRef.current) return

    const viewer = OpenSeadragon({
      element: containerRef.current,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      tileSources: buildTileSource(slideId) as any,
      prefixUrl: 'https://openseadragon.github.io/openseadragon/images/',
      showNavigationControl: false,
      showNavigator: true,
      navigatorPosition: 'BOTTOM_RIGHT',
      navigatorSizeRatio: 0.15,
      navigatorBackground: '#18181b',
      navigatorBorderColor: '#3f3f46',
      animationTime: 0.5,
      blendTime: 0.1,
      constrainDuringPan: true,
      maxZoomPixelRatio: 2,
      minZoomImageRatio: 0.8,
      visibilityRatio: 1,
      zoomPerScroll: 1.5,
    })
    viewerRef.current = viewer
    isReadyRef.current = false
    viewer.addHandler('open', () => {
      isReadyRef.current = true
    })

    return () => {
      isReadyRef.current = false
      viewer.destroy()
      viewerRef.current = null
    }
  }, [])

  // Re-open with a new tile source when slideId changes
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    isReadyRef.current = false
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      viewer.open(buildTileSource(slideId) as any)
    } catch {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      viewer.open(PLACEHOLDER_TILE_SOURCE as any)
    }
  }, [slideId])

  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return

    const apply = () => {
      viewer.clearOverlays()
      if (!overlays || overlays.length === 0) return
      for (const o of overlays) {
        const color = o.color ?? DEFAULT_OVERLAY_COLOR
        const el = document.createElement('div')
        el.style.border = `2px solid ${color}`
        el.style.boxSizing = 'border-box'
        el.style.pointerEvents = 'none'
        el.style.background = `${color}1a`
        el.style.position = 'relative'

        const label = document.createElement('div')
        label.textContent = o.label ?? ''
        label.style.position = 'absolute'
        label.style.top = '0'
        label.style.left = '0'
        label.style.transform = 'translateY(-100%)'
        label.style.padding = '2px 6px'
        label.style.background = color
        label.style.color = '#0b0b0d'
        label.style.font = '600 10px ui-monospace, SFMono-Regular, Menlo, monospace'
        label.style.letterSpacing = '0.04em'
        label.style.whiteSpace = 'nowrap'
        el.appendChild(label)

        // Task 8: clamp coords to [0, 1] to prevent overlay clipping outside slide
        const cx = Math.max(0, Math.min(1, o.x))
        const cy = Math.max(0, Math.min(1, o.y))
        const cw = Math.max(0.001, Math.min(1 - cx, o.w))
        const ch = Math.max(0.001, Math.min(1 - cy, o.h))
        viewer.addOverlay({
          element: el,
          location: new OpenSeadragon.Rect(cx, cy, cw, ch),
        })
      }
    }

    if (isReadyRef.current) {
      apply()
    } else {
      const handler = () => {
        apply()
        viewer.removeHandler('open', handler)
      }
      viewer.addHandler('open', handler)
      return () => {
        viewer.removeHandler('open', handler)
      }
    }
    // slideId is in the deps so overlays are re-applied after a slide swap
    // (which re-opens the OSD viewer and would otherwise drop the overlays).
  }, [overlays, slideId])

  const zoomIn = () => viewerRef.current?.viewport.zoomBy(1.4)
  const zoomOut = () => viewerRef.current?.viewport.zoomBy(1 / 1.4)
  const reset = () => viewerRef.current?.viewport.goHome()

  return (
    <div className={`relative bg-zinc-900 ${className ?? ''}`}>
      {isPlaceholder && <PathMindLogo />}
      <div id="osd-viewer" ref={containerRef} className={`absolute inset-0 ${isPlaceholder ? 'opacity-0 pointer-events-none' : ''}`} />

      {!isPlaceholder && (
        <div className="absolute top-3 left-3 z-10 rounded-md bg-zinc-950/80 px-3 py-1.5 text-xs font-medium text-zinc-100 backdrop-blur border border-zinc-800">
          {slideId}
        </div>
      )}

      {!isPlaceholder && <div className="absolute top-3 right-3 z-10 flex gap-1 rounded-md bg-zinc-950/80 p-1 backdrop-blur border border-zinc-800">
        <button
          type="button"
          onClick={zoomIn}
          className="rounded p-1.5 text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100"
          aria-label="Zoom avant"
        >
          <ZoomIn className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={zoomOut}
          className="rounded p-1.5 text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100"
          aria-label="Zoom arrière"
        >
          <ZoomOut className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={reset}
          className="rounded p-1.5 text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100"
          aria-label="Réinitialiser"
        >
          <Home className="h-4 w-4" />
        </button>
      </div>}
    </div>
  )
}
