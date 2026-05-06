'use client'
import { useEffect, useRef } from 'react'
import OpenSeadragon from 'openseadragon'
import { ZoomIn, ZoomOut, Home } from 'lucide-react'

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
  }, [overlays])

  const zoomIn = () => viewerRef.current?.viewport.zoomBy(1.4)
  const zoomOut = () => viewerRef.current?.viewport.zoomBy(1 / 1.4)
  const reset = () => viewerRef.current?.viewport.goHome()

  return (
    <div className={`relative bg-zinc-900 ${className ?? ''}`}>
      <div id="osd-viewer" ref={containerRef} className="absolute inset-0" />

      <div className="absolute top-3 left-3 z-10 rounded-md bg-zinc-950/80 px-3 py-1.5 text-xs font-medium text-zinc-100 backdrop-blur border border-zinc-800">
        {slideId}
      </div>

      <div className="absolute top-3 right-3 z-10 flex gap-1 rounded-md bg-zinc-950/80 p-1 backdrop-blur border border-zinc-800">
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
      </div>
    </div>
  )
}
