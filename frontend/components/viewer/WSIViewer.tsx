'use client'
import { useEffect, useRef } from 'react'
import OpenSeadragon from 'openseadragon'
import { ZoomIn, ZoomOut, Home } from 'lucide-react'

interface WSIViewerProps {
  slideId: string
  className?: string
}

const TILE_SOURCE = 'https://openseadragon.github.io/example-images/highsmith/highsmith.dzi'

export function WSIViewer({ slideId, className }: WSIViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const viewerRef = useRef<OpenSeadragon.Viewer | null>(null)

  useEffect(() => {
    if (!containerRef.current) return

    const viewer = OpenSeadragon({
      element: containerRef.current,
      tileSources: TILE_SOURCE,
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

    return () => {
      viewer.destroy()
      viewerRef.current = null
    }
  }, [])

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
