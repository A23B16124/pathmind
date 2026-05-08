"use client"

import { useEffect, useRef, useState, useCallback } from "react"
import type OpenSeadragon from "openseadragon"

// All shapes are stored in IMAGE coordinates (pixels of the source image).
// The canvas re-renders on every OSD viewport change so that drawings stay
// pinned to the tissue, not to the screen.

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
  // Glyph rendered as SVG text. Kept ASCII / safe characters.
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
  // Image-pixel coordinates
  points?: { x: number; y: number }[]   // pen
  start?: { x: number; y: number }      // arrow / rect / circle / measure / text / symbol
  end?: { x: number; y: number }        // arrow / rect / circle / measure
  text?: string                         // text / symbol label
  symbol?: PathMindSymbol               // symbol annotation
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
  micronsPerPixel: number   // image scale, default 0.25 µm/px @ 40×
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
  const [imageSize, setImageSize] = useState<{ w: number; h: number }>({ w: 1, h: 1 })

  // Convert client (pointer) → image px.
  // OSD's viewport.pointFromPixel / viewportToImageCoordinates only read .x / .y
  // off their argument, so a plain {x, y} object works (no need for the
  // OpenSeadragon.Point ctor — which lives on the imported module, not window).
  const clientToImage = useCallback(
    (clientX: number, clientY: number): { x: number; y: number } | null => {
      if (!viewer || !containerRef.current) return null
      const rect = containerRef.current.getBoundingClientRect()
      const local = { x: clientX - rect.left, y: clientY - rect.top }
      try {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const vp = viewer.viewport.pointFromPixel(local as any)
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const img = viewer.viewport.viewportToImageCoordinates(vp as any)
        return { x: img.x, y: img.y }
      } catch {
        return null
      }
    },
    [viewer]
  )

  // Convert image px → canvas px (for rendering)
  const imageToCanvas = useCallback(
    (pt: { x: number; y: number }): { x: number; y: number } | null => {
      if (!viewer) return null
      try {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const vp = (viewer.viewport as any).imageToViewportCoordinates(pt.x, pt.y)
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const px = (viewer.viewport as any).pixelFromPoint(vp, true)
        return { x: px.x, y: px.y }
      } catch {
        return null
      }
    },
    [viewer]
  )

  // Resize canvas to viewer size + redraw
  const redraw = useCallback(() => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container) return

    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    const rect = container.getBoundingClientRect()
    const w = rect.width
    const h = rect.height
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

    // Render persisted shapes
    for (const s of shapes) {
      if (s.slideIndex !== slideIndex) continue
      drawShape(ctx, s, imageToCanvas, micronsPerPixel, hoverShapeId === s.id)
    }

    // Render draft (in-flight)
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
      drawShape(ctx, draftShape, imageToCanvas, micronsPerPixel, true)
      ctx.restore()
    }
  }, [shapes, slideIndex, draft, color, strokeWidth, micronsPerPixel, imageToCanvas, hoverShapeId, caseId])

  // Hook OSD viewport-change for live redraw on zoom/pan
  useEffect(() => {
    if (!viewer) return
    const handler = () => redraw()
    viewer.addHandler("update-viewport", handler)
    viewer.addHandler("animation", handler)
    viewer.addHandler("open", handler)
    viewer.addHandler("resize", handler)
    redraw()
    // capture image dimensions
    const captureSize = () => {
      try {
        const item = viewer.world.getItemAt(0)
        if (item) {
          const sz = item.getContentSize()
          setImageSize({ w: sz.x, h: sz.y })
        }
      } catch {}
    }
    captureSize()
    viewer.addHandler("open", captureSize)
    return () => {
      viewer.removeHandler("update-viewport", handler)
      viewer.removeHandler("animation", handler)
      viewer.removeHandler("open", handler)
      viewer.removeHandler("resize", handler)
      viewer.removeHandler("open", captureSize)
    }
  }, [viewer, redraw])

  // Window resize -> redraw
  useEffect(() => {
    const onR = () => redraw()
    window.addEventListener("resize", onR)
    return () => window.removeEventListener("resize", onR)
  }, [redraw])

  // Pointer handlers — only active when a tool is selected
  const isDrawing = tool !== "select"

  const handlePointerDown = (e: React.PointerEvent) => {
    if (!isDrawing || !caseId) return
    const img = clientToImage(e.clientX, e.clientY)
    if (!img) return
    e.preventDefault()
    ;(e.target as HTMLElement).setPointerCapture(e.pointerId)

    if (tool === "pen") {
      setDraft({ type: "pen", points: [img] })
    } else if (tool === "arrow" || tool === "rect" || tool === "circle" || tool === "measure") {
      setDraft({ type: tool, start: img, end: img })
    } else if (tool === "text") {
      const rect = containerRef.current?.getBoundingClientRect()
      if (!rect) return
      setTextInput({
        x: img.x,
        y: img.y,
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
      // Hit-test top shape and remove
      const hit = hitTestShape(e.clientX, e.clientY, shapes, slideIndex, imageToCanvas)
      if (hit) onRemoveShape(hit.id)
    }
  }

  const handlePointerMove = (e: React.PointerEvent) => {
    if (tool === "eraser") {
      const hit = hitTestShape(e.clientX, e.clientY, shapes, slideIndex, imageToCanvas)
      setHoverShapeId(hit?.id ?? null)
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

    if (draft.type === "pen") {
      // Pen: accept stroke as soon as it has 2+ points; tiny click → drop a single dot
      if (draft.points && draft.points.length >= 2) {
        onAddShape({ ...base, type: "pen", points: draft.points })
      } else if (draft.points && draft.points.length === 1) {
        // single click → small dot (2-point segment of 1px length)
        const p = draft.points[0]
        onAddShape({
          ...base,
          type: "pen",
          points: [p, { x: p.x + 1, y: p.y + 1 }],
        })
      }
    } else if (
      (draft.type === "arrow" || draft.type === "rect" || draft.type === "circle" || draft.type === "measure") &&
      draft.start &&
      draft.end
    ) {
      const dx = draft.end.x - draft.start.x
      const dy = draft.end.y - draft.start.y
      const moved = Math.hypot(dx, dy)
      if (moved > 2) {
        onAddShape({ ...base, type: draft.type, start: draft.start, end: draft.end })
      } else {
        // Single click → place a default-sized shape so the user gets immediate feedback.
        // Size is in IMAGE pixels: ~150 px ≈ 37 µm @ 0.25 µm/px (small but visible).
        const defSize = 150
        const a = draft.start
        let endPt = draft.end
        if (draft.type === "arrow") {
          endPt = { x: a.x + defSize, y: a.y - defSize / 2 }
        } else if (draft.type === "rect") {
          endPt = { x: a.x + defSize, y: a.y + defSize * 0.7 }
        } else if (draft.type === "circle") {
          endPt = { x: a.x + defSize / 2, y: a.y }
        } else if (draft.type === "measure") {
          endPt = { x: a.x + defSize, y: a.y }
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
    const id = `s-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    onAddShape({
      id,
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
      className="absolute inset-0"
      style={{ cursor, pointerEvents, zIndex: 5 }}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerLeave={handlePointerUp}
    >
      <canvas ref={canvasRef} className="absolute inset-0" style={{ pointerEvents: "none" }} />

      {/* Inline text input */}
      {textInput && (
        <div
          className="absolute z-10"
          style={{
            left: textInput.client.left,
            top: textInput.client.top,
          }}
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

      {/* Active-tool hint (top-left of viewer when in drawing mode) */}
      {isDrawing && (
        <div className="absolute top-[110px] left-3 z-10 bg-[var(--accent)] text-[var(--paper)] px-3 py-1.5 font-mono text-[10px] uppercase tracking-widest pointer-events-none flex items-center gap-2 shadow-lg">
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

      {/* Image-size hint (debug, shows the assumed scale) */}
      {imageSize.w > 1 && (
        <div className="absolute bottom-2 left-2 font-mono text-[10px] text-[var(--paper)]/60 bg-black/30 px-1.5 py-0.5 pointer-events-none">
          {imageSize.w}×{imageSize.h} px · {micronsPerPixel} µm/px
        </div>
      )}
    </div>
  )
}

// ──────────────────────────────────────────────────────────────────────────
// Drawing helpers
// ──────────────────────────────────────────────────────────────────────────

function drawShape(
  ctx: CanvasRenderingContext2D,
  s: Shape,
  imageToCanvas: (pt: { x: number; y: number }) => { x: number; y: number } | null,
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
      const c = imageToCanvas(p)
      if (!c) continue
      if (first) {
        ctx.moveTo(c.x, c.y)
        first = false
      } else {
        ctx.lineTo(c.x, c.y)
      }
    }
    ctx.stroke()
  } else if (s.type === "arrow" && s.start && s.end) {
    const a = imageToCanvas(s.start)
    const b = imageToCanvas(s.end)
    if (a && b) drawArrow(ctx, a.x, a.y, b.x, b.y)
  } else if (s.type === "rect" && s.start && s.end) {
    const a = imageToCanvas(s.start)
    const b = imageToCanvas(s.end)
    if (a && b) {
      ctx.strokeRect(Math.min(a.x, b.x), Math.min(a.y, b.y), Math.abs(b.x - a.x), Math.abs(b.y - a.y))
    }
  } else if (s.type === "circle" && s.start && s.end) {
    const a = imageToCanvas(s.start)
    const b = imageToCanvas(s.end)
    if (a && b) {
      const r = Math.hypot(b.x - a.x, b.y - a.y)
      ctx.beginPath()
      ctx.arc(a.x, a.y, r, 0, Math.PI * 2)
      ctx.stroke()
    }
  } else if (s.type === "measure" && s.start && s.end) {
    const a = imageToCanvas(s.start)
    const b = imageToCanvas(s.end)
    if (a && b) {
      // Distance in image-px space
      const dxImg = s.end.x - s.start.x
      const dyImg = s.end.y - s.start.y
      const distPx = Math.hypot(dxImg, dyImg)
      const distUm = distPx * mppx
      const distLabel = distUm < 1000 ? `${distUm.toFixed(1)} µm` : `${(distUm / 1000).toFixed(2)} mm`

      // Line + tick marks
      ctx.beginPath()
      ctx.moveTo(a.x, a.y)
      ctx.lineTo(b.x, b.y)
      ctx.stroke()

      // Endcaps perpendicular
      const angle = Math.atan2(b.y - a.y, b.x - a.x)
      const perp = angle + Math.PI / 2
      const cap = 7
      for (const p of [a, b]) {
        ctx.beginPath()
        ctx.moveTo(p.x + Math.cos(perp) * cap, p.y + Math.sin(perp) * cap)
        ctx.lineTo(p.x - Math.cos(perp) * cap, p.y - Math.sin(perp) * cap)
        ctx.stroke()
      }

      // Label background + text
      const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
      ctx.font = "600 12px JetBrains Mono, ui-monospace, monospace"
      const metrics = ctx.measureText(distLabel)
      const padX = 6
      const padY = 4
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
    }
  } else if (s.type === "text" && s.start && s.text) {
    const a = imageToCanvas(s.start)
    if (a) {
      ctx.font = "500 14px Newsreader, Georgia, serif"
      const metrics = ctx.measureText(s.text)
      const padX = 8
      const padY = 5
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
    }
  } else if (s.type === "symbol" && s.start && s.symbol) {
    const a = imageToCanvas(s.start)
    if (a) {
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
      // Label
      ctx.font = "500 11px JetBrains Mono, monospace"
      ctx.fillStyle = "#1c1a16"
      const labelW = ctx.measureText(s.symbol.label).width + 8
      ctx.fillStyle = "rgba(244, 241, 234, 0.95)"
      ctx.fillRect(a.x - labelW / 2, a.y + r + 2, labelW, 16)
      ctx.strokeStyle = s.color
      ctx.lineWidth = 1
      ctx.strokeRect(a.x - labelW / 2, a.y + r + 2, labelW, 16)
      ctx.fillStyle = "#1c1a16"
      ctx.fillText(s.symbol.label, a.x, a.y + r + 11)
    }
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

function hitTestShape(
  clientX: number,
  clientY: number,
  shapes: Shape[],
  slideIndex: number,
  imageToCanvas: (pt: { x: number; y: number }) => { x: number; y: number } | null
): Shape | null {
  // Iterate from latest (top) to oldest
  for (let i = shapes.length - 1; i >= 0; i--) {
    const s = shapes[i]
    if (s.slideIndex !== slideIndex) continue
    const rect = (document.querySelector(".annotation-canvas-host") as HTMLElement)?.getBoundingClientRect()
    const localX = clientX - (rect?.left ?? 0)
    const localY = clientY - (rect?.top ?? 0)
    const hit = isInsideShape(s, localX, localY, imageToCanvas)
    if (hit) return s
  }
  return null
}

function isInsideShape(
  s: Shape,
  x: number,
  y: number,
  imageToCanvas: (pt: { x: number; y: number }) => { x: number; y: number } | null
): boolean {
  const tol = 8
  if (s.type === "pen" && s.points) {
    for (let i = 1; i < s.points.length; i++) {
      const a = imageToCanvas(s.points[i - 1])
      const b = imageToCanvas(s.points[i])
      if (a && b && distToSegment(x, y, a.x, a.y, b.x, b.y) < tol) return true
    }
  } else if ((s.type === "arrow" || s.type === "measure") && s.start && s.end) {
    const a = imageToCanvas(s.start)
    const b = imageToCanvas(s.end)
    if (a && b && distToSegment(x, y, a.x, a.y, b.x, b.y) < tol) return true
  } else if (s.type === "rect" && s.start && s.end) {
    const a = imageToCanvas(s.start)
    const b = imageToCanvas(s.end)
    if (a && b) {
      const x1 = Math.min(a.x, b.x), x2 = Math.max(a.x, b.x)
      const y1 = Math.min(a.y, b.y), y2 = Math.max(a.y, b.y)
      const onEdge =
        (Math.abs(x - x1) < tol && y >= y1 && y <= y2) ||
        (Math.abs(x - x2) < tol && y >= y1 && y <= y2) ||
        (Math.abs(y - y1) < tol && x >= x1 && x <= x2) ||
        (Math.abs(y - y2) < tol && x >= x1 && x <= x2)
      if (onEdge) return true
    }
  } else if (s.type === "circle" && s.start && s.end) {
    const a = imageToCanvas(s.start)
    const b = imageToCanvas(s.end)
    if (a && b) {
      const r = Math.hypot(b.x - a.x, b.y - a.y)
      const d = Math.hypot(x - a.x, y - a.y)
      if (Math.abs(d - r) < tol) return true
    }
  } else if ((s.type === "text" || s.type === "symbol") && s.start) {
    const a = imageToCanvas(s.start)
    if (a) {
      const dx = x - a.x
      const dy = y - a.y
      if (Math.abs(dx) < 80 && Math.abs(dy) < 40) return true
    }
  }
  return false
}

function distToSegment(px: number, py: number, x1: number, y1: number, x2: number, y2: number): number {
  const dx = x2 - x1
  const dy = y2 - y1
  const lensq = dx * dx + dy * dy
  if (lensq === 0) return Math.hypot(px - x1, py - y1)
  let t = ((px - x1) * dx + (py - y1) * dy) / lensq
  t = Math.max(0, Math.min(1, t))
  const fx = x1 + t * dx
  const fy = y1 + t * dy
  return Math.hypot(px - fx, py - fy)
}
