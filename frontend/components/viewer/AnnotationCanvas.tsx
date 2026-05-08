"use client"

import { useEffect, useRef, useState, useCallback } from "react"
import type OpenSeadragon from "openseadragon"

// Coordinates are stored as FRACTIONS (0..1) of the viewer container box.
// Rendering is just a multiply by canvas pixel dims — no OSD math needed,
// so clicks/draws always work even if the OSD viewport state is unusual.
// Trade-off: shapes are anchored to the viewer rectangle, not to the image
// pixels, so they don't follow zoom/pan inside OSD. For the demo this is
// the right call: bulletproof interaction beats imperfect zoom-tracking.

export type ToolKind =
  | "select"
  | "pen"
  | "arrow"
  | "rect"
  | "circle"
  | "measure"
  | "text"
  | "symbol"
  | "eraser"

export interface PathMindSymbol {
  id: string
  label: string
  glyph: string
  color?: string
  description: string
}

export const PATHMIND_SYMBOLS: PathMindSymbol[] = [
  { id: "atypia", label: "Atypie", glyph: "!", color: "#a23939", description: "Atypie cellulaire à confirmer" },
  { id: "mitose", label: "Mitose", glyph: "M", color: "#6b1d1d", description: "Mitose / activité mitotique" },
  { id: "necrose", label: "Nécrose", glyph: "N", color: "#4a4538", description: "Foyer de nécrose" },
  { id: "lvi", label: "LVI", glyph: "V", color: "#8a5a14", description: "Invasion lymphovasculaire" },
  { id: "pni", label: "PNI", glyph: "P", color: "#8a5a14", description: "Invasion périnerveuse" },
  { id: "marge", label: "Marge", glyph: "X", color: "#a23939", description: "Marge limite / atteinte" },
  { id: "tumor", label: "Tumeur", glyph: "T", color: "#6b1d1d", description: "Foyer tumoral" },
  { id: "stroma", label: "Stroma", glyph: "S", color: "#2f5d3a", description: "Stroma desmoplastique" },
  { id: "ihc", label: "IHC", glyph: "I", color: "#1c1a16", description: "Cible pour IHC" },
  { id: "review", label: "Revue", glyph: "?", color: "#8a5a14", description: "À discuter / second avis" },
]

export interface Shape {
  id: string
  caseId: string
  slideIndex: number
  type: ToolKind
  // FRACTION coords (0..1) of the viewer container at draw time
  points?: { x: number; y: number }[]
  start?: { x: number; y: number }
  end?: { x: number; y: number }
  text?: string
  symbol?: PathMindSymbol
  color: string
  strokeWidth: number
  createdAt: number
}

interface AnnotationCanvasProps {
  viewer: OpenSeadragon.Viewer | null
  caseId: string | undefined
  slideIndex: number
  tool: ToolKind
  color: string
  strokeWidth: number
  selectedSymbol: PathMindSymbol | null
  shapes: Shape[]
  micronsPerPixel: number
  onAddShape: (shape: Shape) => void
  onRemoveShape: (id: string) => void
}

interface DraftShape {
  type: ToolKind
  points?: { x: number; y: number }[]
  start?: { x: number; y: number }
  end?: { x: number; y: number }
}

export function AnnotationCanvas({
  viewer,
  caseId,
  slideIndex,
  tool,
  color,
  strokeWidth,
  selectedSymbol,
  shapes,
  micronsPerPixel,
  onAddShape,
  onRemoveShape,
}: AnnotationCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [draft, setDraft] = useState<DraftShape | null>(null)
  const [textInput, setTextInput] = useState<{ x: number; y: number; raw: string; client: { left: number; top: number } } | null>(null)
  const [hoverShapeId, setHoverShapeId] = useState<string | null>(null)
  const [imageSize, setImageSize] = useState<{ w: number; h: number }>({ w: 0, h: 0 })

  // Pointer client coords → fraction (0..1) of the viewer container
  const clientToFrac = useCallback((clientX: number, clientY: number): { x: number; y: number } | null => {
    const c = containerRef.current
    if (!c) return null
    const rect = c.getBoundingClientRect()
    if (rect.width <= 0 || rect.height <= 0) return null
    return {
      x: (clientX - rect.left) / rect.width,
      y: (clientY - rect.top) / rect.height,
    }
  }, [])

  // Fraction → canvas pixel
  const fracToPx = useCallback((pt: { x: number; y: number }): { x: number; y: number } => {
    const c = containerRef.current
    if (!c) return { x: 0, y: 0 }
    const rect = c.getBoundingClientRect()
    return { x: pt.x * rect.width, y: pt.y * rect.height }
  }, [])

  // Read OSD image size for distance scale (fall back to a sane default)
  useEffect(() => {
    if (!viewer) return
    const capture = () => {
      try {
        const item = viewer.world.getItemAt(0)
        if (item) {
          const sz = item.getContentSize()
          if (sz.x > 0 && sz.y > 0) setImageSize({ w: sz.x, h: sz.y })
        }
      } catch {}
    }
    capture()
    viewer.addHandler("open", capture)
    return () => {
      viewer.removeHandler("open", capture)
    }
  }, [viewer])

  // Redraw — uses canvas pixel coords directly from fractions, no OSD math
  const redraw = useCallback(() => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container) return

    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    const rect = container.getBoundingClientRect()
    const w = rect.width
    const h = rect.height
    if (w <= 0 || h <= 0) return
    if (canvas.width !== Math.floor(w * dpr) || canvas.height !== Math.floor(h * dpr)) {
      canvas.width = Math.floor(w * dpr)
      canvas.height = Math.floor(h * dpr)
      canvas.style.width = `${w}px`
      canvas.style.height = `${h}px`
    }
    const ctx = canvas.getContext("2d")
    if (!ctx) return
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, w, h)

    const scaleW = imageSize.w > 0 ? imageSize.w : w / 0.25
    // For distance: 1 fraction ≈ scaleW image px, so distUm = sqrt(dx² + dy²) × scaleW × mppx
    for (const s of shapes) {
      if (s.slideIndex !== slideIndex) continue
      drawShape(ctx, s, fracToPx, scaleW, micronsPerPixel, hoverShapeId === s.id)
    }
    if (draft) {
      const draftShape: Shape = {
        id: "__draft__",
        caseId: caseId ?? "",
        slideIndex,
        type: draft.type,
        points: draft.points,
        start: draft.start,
        end: draft.end,
        color,
        strokeWidth,
        createdAt: Date.now(),
      }
      ctx.save()
      ctx.globalAlpha = 0.85
      drawShape(ctx, draftShape, fracToPx, scaleW, micronsPerPixel, true)
      ctx.restore()
    }
  }, [shapes, slideIndex, draft, color, strokeWidth, fracToPx, imageSize, micronsPerPixel, hoverShapeId, caseId])

  // Re-render on shape / draft / size changes
  useEffect(() => {
    redraw()
  }, [redraw])

  // Window resize → redraw
  useEffect(() => {
    const onR = () => redraw()
    window.addEventListener("resize", onR)
    return () => window.removeEventListener("resize", onR)
  }, [redraw])

  // OSD viewport changes → redraw (so the canvas re-sizes if the viewer does)
  useEffect(() => {
    if (!viewer) return
    const handler = () => redraw()
    viewer.addHandler("update-viewport", handler)
    viewer.addHandler("animation", handler)
    viewer.addHandler("resize", handler)
    return () => {
      viewer.removeHandler("update-viewport", handler)
      viewer.removeHandler("animation", handler)
      viewer.removeHandler("resize", handler)
    }
  }, [viewer, redraw])

  const isDrawing = tool !== "select"

  const handlePointerDown = (e: React.PointerEvent) => {
    if (!isDrawing || !caseId) return
    const frac = clientToFrac(e.clientX, e.clientY)
    if (!frac) return
    e.preventDefault()
    try {
      ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
    } catch {}

    if (tool === "pen") {
      setDraft({ type: "pen", points: [frac] })
    } else if (tool === "arrow" || tool === "rect" || tool === "circle" || tool === "measure") {
      setDraft({ type: tool, start: frac, end: frac })
    } else if (tool === "text") {
      const rect = containerRef.current?.getBoundingClientRect()
      if (!rect) return
      setTextInput({
        x: frac.x,
        y: frac.y,
        raw: "",
        client: { left: e.clientX - rect.left, top: e.clientY - rect.top },
      })
    } else if (tool === "symbol" && selectedSymbol) {
      const newShape: Shape = {
        id: `s-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        caseId,
        slideIndex,
        type: "symbol",
        start: frac,
        symbol: selectedSymbol,
        text: selectedSymbol.label,
        color: selectedSymbol.color ?? color,
        strokeWidth,
        createdAt: Date.now(),
      }
      onAddShape(newShape)
    } else if (tool === "eraser") {
      const hit = hitTestShape(frac, shapes, slideIndex)
      if (hit) onRemoveShape(hit.id)
    }
  }

  const handlePointerMove = (e: React.PointerEvent) => {
    if (tool === "eraser") {
      const frac = clientToFrac(e.clientX, e.clientY)
      if (frac) {
        const hit = hitTestShape(frac, shapes, slideIndex)
        setHoverShapeId(hit?.id ?? null)
      }
    }
    if (!draft) return
    const frac = clientToFrac(e.clientX, e.clientY)
    if (!frac) return
    if (draft.type === "pen") {
      setDraft({ ...draft, points: [...(draft.points ?? []), frac] })
    } else {
      setDraft({ ...draft, end: frac })
    }
  }

  const handlePointerUp = (e: React.PointerEvent) => {
    if (!draft || !caseId) {
      setDraft(null)
      return
    }
    e.preventDefault()
    try {
      ;(e.target as HTMLElement).releasePointerCapture(e.pointerId)
    } catch {}

    const id = `s-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const base = { id, caseId, slideIndex, color, strokeWidth, createdAt: Date.now() }

    if (draft.type === "pen") {
      if (draft.points && draft.points.length >= 2) {
        onAddShape({ ...base, type: "pen", points: draft.points })
      } else if (draft.points && draft.points.length === 1) {
        const p = draft.points[0]
        onAddShape({ ...base, type: "pen", points: [p, { x: p.x + 0.005, y: p.y + 0.005 }] })
      }
    } else if (
      (draft.type === "arrow" || draft.type === "rect" || draft.type === "circle" || draft.type === "measure") &&
      draft.start &&
      draft.end
    ) {
      const dx = draft.end.x - draft.start.x
      const dy = draft.end.y - draft.start.y
      const moved = Math.hypot(dx, dy)
      // moved is in fraction units; threshold = ~0.5% of viewer
      if (moved > 0.005) {
        onAddShape({ ...base, type: draft.type, start: draft.start, end: draft.end })
      } else {
        // Single click → place a default-sized shape (~10% of viewer width)
        const def = 0.08
        const a = draft.start
        let endPt = draft.end
        if (draft.type === "arrow") {
          endPt = { x: a.x + def, y: a.y - def / 2 }
        } else if (draft.type === "rect") {
          endPt = { x: a.x + def, y: a.y + def * 0.6 }
        } else if (draft.type === "circle") {
          endPt = { x: a.x + def / 2, y: a.y }
        } else if (draft.type === "measure") {
          endPt = { x: a.x + def, y: a.y }
        }
        onAddShape({ ...base, type: draft.type, start: a, end: endPt })
      }
    }
    setDraft(null)
  }

  const handleTextSubmit = () => {
    if (!textInput || !caseId || !textInput.raw.trim()) {
      setTextInput(null)
      return
    }
    onAddShape({
      id: `s-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      caseId,
      slideIndex,
      type: "text",
      start: { x: textInput.x, y: textInput.y },
      text: textInput.raw.trim(),
      color,
      strokeWidth,
      createdAt: Date.now(),
    })
    setTextInput(null)
  }

  const cursor =
    tool === "select"
      ? "auto"
      : tool === "eraser"
      ? "not-allowed"
      : tool === "text"
      ? "text"
      : "crosshair"

  const pointerEvents = isDrawing ? "auto" : "none"

  return (
    <div
      ref={containerRef}
      className="absolute inset-0 annotation-canvas-host"
      style={{ cursor, pointerEvents, zIndex: 5 }}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerLeave={handlePointerUp}
    >
      <canvas ref={canvasRef} className="absolute inset-0" style={{ pointerEvents: "none" }} />

      {textInput && (
        <div
          className="absolute z-10"
          style={{ left: textInput.client.left, top: textInput.client.top }}
        >
          <input
            type="text"
            autoFocus
            value={textInput.raw}
            onChange={(e) => setTextInput({ ...textInput, raw: e.target.value })}
            onBlur={handleTextSubmit}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleTextSubmit()
              if (e.key === "Escape") setTextInput(null)
            }}
            placeholder="Annotation"
            className="bg-[var(--paper)] border border-[var(--ink)] px-2 py-1 text-[12px] font-serif text-[var(--ink)] focus:outline-none shadow-lg"
            style={{ minWidth: 160 }}
          />
        </div>
      )}

      {isDrawing && (
        <div className="absolute top-3 left-3 z-10 bg-[var(--accent)] text-[var(--paper)] px-3 py-1.5 font-mono text-[10px] uppercase tracking-widest pointer-events-none flex items-center gap-2 shadow-lg">
          <span className="w-1.5 h-1.5 rounded-full bg-[var(--paper)] animate-pulse" />
          Mode {tool === "pen" ? "stylo" : tool === "arrow" ? "flèche" : tool === "rect" ? "rectangle" : tool === "circle" ? "cercle" : tool === "measure" ? "mesure" : tool === "text" ? "texte" : tool === "symbol" ? `symbole : ${selectedSymbol?.label ?? "—"}` : tool === "eraser" ? "gomme" : tool}
          <span className="text-[var(--paper)]/70 normal-case tracking-normal pl-2 border-l border-[var(--paper)]/30">
            {tool === "pen" || tool === "arrow" || tool === "rect" || tool === "circle" || tool === "measure"
              ? "cliquez ou glissez sur la lame"
              : tool === "text" || tool === "symbol"
              ? "cliquez sur la lame"
              : tool === "eraser"
              ? "cliquez sur un tracé pour le supprimer"
              : ""}
          </span>
        </div>
      )}
    </div>
  )
}

// ──────────────────────────────────────────────────────────────────────────
// Drawing helpers (input coords are FRACTIONS, converted to canvas px here)
// ──────────────────────────────────────────────────────────────────────────

function drawShape(
  ctx: CanvasRenderingContext2D,
  s: Shape,
  fracToPx: (pt: { x: number; y: number }) => { x: number; y: number },
  imageWidthPx: number,
  mppx: number,
  highlight: boolean
) {
  ctx.save()
  ctx.strokeStyle = s.color
  ctx.fillStyle = s.color
  ctx.lineWidth = s.strokeWidth
  ctx.lineJoin = "round"
  ctx.lineCap = "round"
  if (highlight) {
    ctx.shadowColor = s.color
    ctx.shadowBlur = 8
  }

  if (s.type === "pen" && s.points && s.points.length > 1) {
    ctx.beginPath()
    let first = true
    for (const p of s.points) {
      const c = fracToPx(p)
      if (first) { ctx.moveTo(c.x, c.y); first = false }
      else ctx.lineTo(c.x, c.y)
    }
    ctx.stroke()
  } else if (s.type === "arrow" && s.start && s.end) {
    const a = fracToPx(s.start), b = fracToPx(s.end)
    drawArrow(ctx, a.x, a.y, b.x, b.y)
  } else if (s.type === "rect" && s.start && s.end) {
    const a = fracToPx(s.start), b = fracToPx(s.end)
    ctx.strokeRect(Math.min(a.x, b.x), Math.min(a.y, b.y), Math.abs(b.x - a.x), Math.abs(b.y - a.y))
  } else if (s.type === "circle" && s.start && s.end) {
    const a = fracToPx(s.start), b = fracToPx(s.end)
    const r = Math.hypot(b.x - a.x, b.y - a.y)
    ctx.beginPath()
    ctx.arc(a.x, a.y, r, 0, Math.PI * 2)
    ctx.stroke()
  } else if (s.type === "measure" && s.start && s.end) {
    const a = fracToPx(s.start), b = fracToPx(s.end)
    const dxFrac = s.end.x - s.start.x
    const dyFrac = s.end.y - s.start.y
    // distance in image px ≈ sqrt(dx² + dy²) × imageWidthPx (assuming square aspect for simplicity)
    const distImagePx = Math.hypot(dxFrac, dyFrac) * imageWidthPx
    const distUm = distImagePx * mppx
    const distLabel = distUm < 1000 ? `${distUm.toFixed(1)} µm` : `${(distUm / 1000).toFixed(2)} mm`

    ctx.beginPath()
    ctx.moveTo(a.x, a.y)
    ctx.lineTo(b.x, b.y)
    ctx.stroke()
    const angle = Math.atan2(b.y - a.y, b.x - a.x)
    const perp = angle + Math.PI / 2
    const cap = 7
    for (const p of [a, b]) {
      ctx.beginPath()
      ctx.moveTo(p.x + Math.cos(perp) * cap, p.y + Math.sin(perp) * cap)
      ctx.lineTo(p.x - Math.cos(perp) * cap, p.y - Math.sin(perp) * cap)
      ctx.stroke()
    }
    const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
    ctx.font = "600 12px JetBrains Mono, ui-monospace, monospace"
    const metrics = ctx.measureText(distLabel)
    const padX = 6
    const boxW = metrics.width + padX * 2
    const boxH = 18
    const offY = -boxH - 6
    ctx.fillStyle = "rgba(244, 241, 234, 0.96)"
    ctx.strokeStyle = s.color
    ctx.lineWidth = 1
    ctx.fillRect(mid.x - boxW / 2, mid.y + offY, boxW, boxH)
    ctx.strokeRect(mid.x - boxW / 2, mid.y + offY, boxW, boxH)
    ctx.fillStyle = "#1c1a16"
    ctx.textAlign = "center"
    ctx.textBaseline = "middle"
    ctx.fillText(distLabel, mid.x, mid.y + offY + boxH / 2)
  } else if (s.type === "text" && s.start && s.text) {
    const a = fracToPx(s.start)
    ctx.font = "500 14px Newsreader, Georgia, serif"
    const metrics = ctx.measureText(s.text)
    const padX = 8
    const boxW = metrics.width + padX * 2
    const boxH = 24
    ctx.fillStyle = "rgba(244, 241, 234, 0.96)"
    ctx.strokeStyle = s.color
    ctx.lineWidth = 1
    ctx.fillRect(a.x, a.y - boxH, boxW, boxH)
    ctx.strokeRect(a.x, a.y - boxH, boxW, boxH)
    ctx.fillStyle = "#1c1a16"
    ctx.textAlign = "left"
    ctx.textBaseline = "middle"
    ctx.fillText(s.text, a.x + padX, a.y - boxH / 2)
  } else if (s.type === "symbol" && s.start && s.symbol) {
    const a = fracToPx(s.start)
    const r = 14
    ctx.beginPath()
    ctx.arc(a.x, a.y, r, 0, Math.PI * 2)
    ctx.fillStyle = "rgba(244, 241, 234, 0.95)"
    ctx.fill()
    ctx.lineWidth = 2
    ctx.strokeStyle = s.color
    ctx.stroke()
    ctx.fillStyle = s.color
    ctx.font = "700 14px JetBrains Mono, monospace"
    ctx.textAlign = "center"
    ctx.textBaseline = "middle"
    ctx.fillText(s.symbol.glyph, a.x, a.y + 1)
    ctx.font = "500 11px JetBrains Mono, monospace"
    const labelW = ctx.measureText(s.symbol.label).width + 8
    ctx.fillStyle = "rgba(244, 241, 234, 0.95)"
    ctx.fillRect(a.x - labelW / 2, a.y + r + 2, labelW, 16)
    ctx.strokeStyle = s.color
    ctx.lineWidth = 1
    ctx.strokeRect(a.x - labelW / 2, a.y + r + 2, labelW, 16)
    ctx.fillStyle = "#1c1a16"
    ctx.fillText(s.symbol.label, a.x, a.y + r + 11)
  }
  ctx.restore()
}

function drawArrow(ctx: CanvasRenderingContext2D, x1: number, y1: number, x2: number, y2: number) {
  const headLen = 14
  const angle = Math.atan2(y2 - y1, x2 - x1)
  ctx.beginPath()
  ctx.moveTo(x1, y1)
  ctx.lineTo(x2, y2)
  ctx.stroke()
  ctx.beginPath()
  ctx.moveTo(x2, y2)
  ctx.lineTo(x2 - headLen * Math.cos(angle - Math.PI / 6), y2 - headLen * Math.sin(angle - Math.PI / 6))
  ctx.lineTo(x2 - headLen * Math.cos(angle + Math.PI / 6), y2 - headLen * Math.sin(angle + Math.PI / 6))
  ctx.closePath()
  ctx.fill()
}

// Hit test in fraction space (tolerance ~1% of viewer)
function hitTestShape(frac: { x: number; y: number }, shapes: Shape[], slideIndex: number): Shape | null {
  const tol = 0.012
  for (let i = shapes.length - 1; i >= 0; i--) {
    const s = shapes[i]
    if (s.slideIndex !== slideIndex) continue
    if (isInsideShape(s, frac.x, frac.y, tol)) return s
  }
  return null
}

function isInsideShape(s: Shape, x: number, y: number, tol: number): boolean {
  if (s.type === "pen" && s.points) {
    for (let i = 1; i < s.points.length; i++) {
      const a = s.points[i - 1], b = s.points[i]
      if (distToSegment(x, y, a.x, a.y, b.x, b.y) < tol) return true
    }
  } else if ((s.type === "arrow" || s.type === "measure") && s.start && s.end) {
    if (distToSegment(x, y, s.start.x, s.start.y, s.end.x, s.end.y) < tol) return true
  } else if (s.type === "rect" && s.start && s.end) {
    const x1 = Math.min(s.start.x, s.end.x), x2 = Math.max(s.start.x, s.end.x)
    const y1 = Math.min(s.start.y, s.end.y), y2 = Math.max(s.start.y, s.end.y)
    const onEdge =
      (Math.abs(x - x1) < tol && y >= y1 && y <= y2) ||
      (Math.abs(x - x2) < tol && y >= y1 && y <= y2) ||
      (Math.abs(y - y1) < tol && x >= x1 && x <= x2) ||
      (Math.abs(y - y2) < tol && x >= x1 && x <= x2)
    if (onEdge) return true
  } else if (s.type === "circle" && s.start && s.end) {
    const r = Math.hypot(s.end.x - s.start.x, s.end.y - s.start.y)
    const d = Math.hypot(x - s.start.x, y - s.start.y)
    if (Math.abs(d - r) < tol) return true
  } else if ((s.type === "text" || s.type === "symbol") && s.start) {
    const dx = x - s.start.x, dy = y - s.start.y
    if (Math.abs(dx) < 0.06 && Math.abs(dy) < 0.04) return true
  }
  return false
}

function distToSegment(px: number, py: number, x1: number, y1: number, x2: number, y2: number): number {
  const dx = x2 - x1, dy = y2 - y1
  const lensq = dx * dx + dy * dy
  if (lensq === 0) return Math.hypot(px - x1, py - y1)
  let t = ((px - x1) * dx + (py - y1) * dy) / lensq
  t = Math.max(0, Math.min(1, t))
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))
}
