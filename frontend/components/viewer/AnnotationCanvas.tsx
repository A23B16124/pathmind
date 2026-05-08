"use client"

import { useEffect, useRef, useState, useCallback } from "react"
import OpenSeadragon from "openseadragon"
import {
  PATHMIND_SYMBOLS,
  type ToolKind,
  type PathMindSymbol,
  type Shape,
} from "./AnnotationTypes"

export { PATHMIND_SYMBOLS }
export type { ToolKind, PathMindSymbol, Shape }

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
  const [textInput, setTextInput] = useState<{
    img: { x: number; y: number }
    raw: string
    client: { left: number; top: number }
  } | null>(null)
  const [hoverShapeId, setHoverShapeId] = useState<string | null>(null)
  const [, forceTick] = useState(0)

  // Pointer client coords → IMAGE pixel coords (via OSD)
  const clientToImage = useCallback(
    (clientX: number, clientY: number): { x: number; y: number } | null => {
      if (!viewer) return null
      const c = containerRef.current
      if (!c) return null
      const rect = c.getBoundingClientRect()
      if (rect.width <= 0 || rect.height <= 0) return null
      try {
        const px = clientX - rect.left
        const py = clientY - rect.top
        const vp = viewer.viewport.pointFromPixel(new OpenSeadragon.Point(px, py), true)
        const ic = viewer.viewport.viewportToImageCoordinates(vp)
        return { x: ic.x, y: ic.y }
      } catch {
        return null
      }
    },
    [viewer]
  )

  // IMAGE pixel coords → canvas/viewer pixel coords
  const imageToPx = useCallback(
    (pt: { x: number; y: number }): { x: number; y: number } => {
      if (!viewer) return { x: 0, y: 0 }
      try {
        const vp = viewer.viewport.imageToViewportCoordinates(pt.x, pt.y)
        const px = viewer.viewport.pixelFromPoint(vp, true)
        return { x: px.x, y: px.y }
      } catch {
        return { x: 0, y: 0 }
      }
    },
    [viewer]
  )

  // Image-pixel tolerance equivalent to ~12 viewer-pixels (for hit tests)
  const pxToleranceInImage = useCallback(
    (viewerPx: number): number => {
      if (!viewer) return viewerPx
      try {
        const v0 = viewer.viewport.pointFromPixel(new OpenSeadragon.Point(0, 0), true)
        const v1 = viewer.viewport.pointFromPixel(new OpenSeadragon.Point(viewerPx, 0), true)
        const i0 = viewer.viewport.viewportToImageCoordinates(v0)
        const i1 = viewer.viewport.viewportToImageCoordinates(v1)
        return Math.abs(i1.x - i0.x)
      } catch {
        return viewerPx
      }
    },
    [viewer]
  )

  // Redraw — converts IMAGE coords to viewer-pixels through OSD
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

    if (!viewer) return

    for (const s of shapes) {
      if (s.slideIndex !== slideIndex) continue
      drawShape(ctx, s, imageToPx, micronsPerPixel, hoverShapeId === s.id)
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
      drawShape(ctx, draftShape, imageToPx, micronsPerPixel, true)
      ctx.restore()
    }
  }, [shapes, slideIndex, draft, color, strokeWidth, imageToPx, micronsPerPixel, hoverShapeId, caseId, viewer])

  useEffect(() => {
    redraw()
  }, [redraw])

  useEffect(() => {
    const onR = () => redraw()
    window.addEventListener("resize", onR)
    return () => window.removeEventListener("resize", onR)
  }, [redraw])

  // OSD events → redraw on every viewport change so annotations follow zoom/pan
  useEffect(() => {
    if (!viewer) return
    const handler = () => {
      forceTick((t) => t + 1)
    }
    viewer.addHandler("update-viewport", handler)
    viewer.addHandler("animation", handler)
    viewer.addHandler("animation-finish", handler)
    viewer.addHandler("zoom", handler)
    viewer.addHandler("pan", handler)
    viewer.addHandler("resize", handler)
    viewer.addHandler("open", handler)
    return () => {
      viewer.removeHandler("update-viewport", handler)
      viewer.removeHandler("animation", handler)
      viewer.removeHandler("animation-finish", handler)
      viewer.removeHandler("zoom", handler)
      viewer.removeHandler("pan", handler)
      viewer.removeHandler("resize", handler)
      viewer.removeHandler("open", handler)
    }
  }, [viewer])

  const isDrawing = tool !== "select"

  const handlePointerDown = (e: React.PointerEvent) => {
    if (!isDrawing || !caseId) return
    const img = clientToImage(e.clientX, e.clientY)
    if (!img) return
    e.preventDefault()
    try {
      ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
    } catch {}

    if (tool === "pen") {
      setDraft({ type: "pen", points: [img] })
    } else if (tool === "arrow" || tool === "rect" || tool === "circle" || tool === "measure") {
      setDraft({ type: tool, start: img, end: img })
    } else if (tool === "text") {
      const rect = containerRef.current?.getBoundingClientRect()
      if (!rect) return
      setTextInput({
        img,
        raw: "",
        client: { left: e.clientX - rect.left, top: e.clientY - rect.top },
      })
    } else if (tool === "symbol" && selectedSymbol) {
      const newShape: Shape = {
        id: `s-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        caseId,
        slideIndex,
        type: "symbol",
        start: img,
        symbol: selectedSymbol,
        text: selectedSymbol.label,
        color: selectedSymbol.color ?? color,
        strokeWidth,
        createdAt: Date.now(),
      }
      onAddShape(newShape)
    } else if (tool === "eraser") {
      const tol = pxToleranceInImage(14)
      const hit = hitTestShape(img, shapes, slideIndex, tol)
      if (hit) onRemoveShape(hit.id)
    }
  }

  const handlePointerMove = (e: React.PointerEvent) => {
    if (tool === "eraser") {
      const img = clientToImage(e.clientX, e.clientY)
      if (img) {
        const tol = pxToleranceInImage(14)
        const hit = hitTestShape(img, shapes, slideIndex, tol)
        setHoverShapeId(hit?.id ?? null)
      }
    }
    if (!draft) return
    const img = clientToImage(e.clientX, e.clientY)
    if (!img) return
    if (draft.type === "pen") {
      setDraft({ ...draft, points: [...(draft.points ?? []), img] })
    } else {
      setDraft({ ...draft, end: img })
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
    const movedThresh = pxToleranceInImage(6)

    if (draft.type === "pen") {
      if (draft.points && draft.points.length >= 2) {
        onAddShape({ ...base, type: "pen", points: draft.points })
      } else if (draft.points && draft.points.length === 1) {
        const p = draft.points[0]
        const off = pxToleranceInImage(2)
        onAddShape({ ...base, type: "pen", points: [p, { x: p.x + off, y: p.y + off }] })
      }
    } else if (
      (draft.type === "arrow" || draft.type === "rect" || draft.type === "circle" || draft.type === "measure") &&
      draft.start &&
      draft.end
    ) {
      const moved = Math.hypot(draft.end.x - draft.start.x, draft.end.y - draft.start.y)
      if (moved > movedThresh) {
        onAddShape({ ...base, type: draft.type, start: draft.start, end: draft.end })
      } else {
        // Single click → place a default-sized shape (~80 viewer-px wide, expressed in image px)
        const def = pxToleranceInImage(80)
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
      start: textInput.img,
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
// Drawing — input coords are in IMAGE pixels, converted via imageToPx().
// Visual sizes (stroke, glyph radius, label box) stay constant in viewer-px.
// ──────────────────────────────────────────────────────────────────────────

function drawShape(
  ctx: CanvasRenderingContext2D,
  s: Shape,
  imageToPx: (pt: { x: number; y: number }) => { x: number; y: number },
  mppx: number,
  highlight: boolean
) {
  ctx.save()
  // Soft dark halo so fluo strokes pop on the bright slide tissue
  ctx.shadowColor = "rgba(0, 0, 0, 0.55)"
  ctx.shadowBlur = 4
  ctx.strokeStyle = s.color
  ctx.fillStyle = s.color
  ctx.lineWidth = s.strokeWidth
  ctx.lineJoin = "round"
  ctx.lineCap = "round"
  if (highlight) {
    ctx.shadowColor = s.color
    ctx.shadowBlur = 10
  }

  if (s.type === "pen" && s.points && s.points.length > 1) {
    ctx.beginPath()
    let first = true
    for (const p of s.points) {
      const c = imageToPx(p)
      if (first) { ctx.moveTo(c.x, c.y); first = false }
      else ctx.lineTo(c.x, c.y)
    }
    ctx.stroke()
  } else if (s.type === "arrow" && s.start && s.end) {
    const a = imageToPx(s.start), b = imageToPx(s.end)
    drawArrow(ctx, a.x, a.y, b.x, b.y)
  } else if (s.type === "rect" && s.start && s.end) {
    const a = imageToPx(s.start), b = imageToPx(s.end)
    ctx.strokeRect(Math.min(a.x, b.x), Math.min(a.y, b.y), Math.abs(b.x - a.x), Math.abs(b.y - a.y))
  } else if (s.type === "circle" && s.start && s.end) {
    const a = imageToPx(s.start), b = imageToPx(s.end)
    const r = Math.hypot(b.x - a.x, b.y - a.y)
    ctx.beginPath()
    ctx.arc(a.x, a.y, r, 0, Math.PI * 2)
    ctx.stroke()
  } else if (s.type === "measure" && s.start && s.end) {
    const a = imageToPx(s.start), b = imageToPx(s.end)
    // Distance is in IMAGE pixels regardless of zoom
    const distImagePx = Math.hypot(s.end.x - s.start.x, s.end.y - s.start.y)
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
    ctx.shadowBlur = 0
    ctx.font = "600 12px JetBrains Mono, ui-monospace, monospace"
    const metrics = ctx.measureText(distLabel)
    const padX = 6
    const boxW = metrics.width + padX * 2
    const boxH = 18
    const offY = -boxH - 6
    ctx.fillStyle = "rgba(28, 26, 22, 0.92)"
    ctx.strokeStyle = s.color
    ctx.lineWidth = 1
    ctx.fillRect(mid.x - boxW / 2, mid.y + offY, boxW, boxH)
    ctx.strokeRect(mid.x - boxW / 2, mid.y + offY, boxW, boxH)
    ctx.fillStyle = s.color
    ctx.textAlign = "center"
    ctx.textBaseline = "middle"
    ctx.fillText(distLabel, mid.x, mid.y + offY + boxH / 2)
  } else if (s.type === "text" && s.start && s.text) {
    const a = imageToPx(s.start)
    ctx.shadowBlur = 0
    ctx.font = "500 14px Newsreader, Georgia, serif"
    const metrics = ctx.measureText(s.text)
    const padX = 8
    const boxW = metrics.width + padX * 2
    const boxH = 24
    ctx.fillStyle = "rgba(28, 26, 22, 0.92)"
    ctx.strokeStyle = s.color
    ctx.lineWidth = 1
    ctx.fillRect(a.x, a.y - boxH, boxW, boxH)
    ctx.strokeRect(a.x, a.y - boxH, boxW, boxH)
    ctx.fillStyle = s.color
    ctx.textAlign = "left"
    ctx.textBaseline = "middle"
    ctx.fillText(s.text, a.x + padX, a.y - boxH / 2)
  } else if (s.type === "symbol" && s.start && s.symbol) {
    const a = imageToPx(s.start)
    const r = 14
    ctx.shadowBlur = 0
    ctx.beginPath()
    ctx.arc(a.x, a.y, r, 0, Math.PI * 2)
    ctx.fillStyle = "rgba(28, 26, 22, 0.92)"
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
    ctx.fillStyle = "rgba(28, 26, 22, 0.92)"
    ctx.fillRect(a.x - labelW / 2, a.y + r + 2, labelW, 16)
    ctx.strokeStyle = s.color
    ctx.lineWidth = 1
    ctx.strokeRect(a.x - labelW / 2, a.y + r + 2, labelW, 16)
    ctx.fillStyle = s.color
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

// Hit test in IMAGE pixel space (tol comes from caller, derived from viewer-px)
function hitTestShape(
  img: { x: number; y: number },
  shapes: Shape[],
  slideIndex: number,
  tol: number
): Shape | null {
  for (let i = shapes.length - 1; i >= 0; i--) {
    const s = shapes[i]
    if (s.slideIndex !== slideIndex) continue
    if (isInsideShape(s, img.x, img.y, tol)) return s
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
    // Slightly larger box (text/symbol stay constant in viewer-px so tol scales)
    const box = tol * 6
    const dx = x - s.start.x, dy = y - s.start.y
    if (Math.abs(dx) < box && Math.abs(dy) < box) return true
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
