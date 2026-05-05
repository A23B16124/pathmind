'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame, type ThreeEvent } from '@react-three/fiber'
import { CameraControls, Html } from '@react-three/drei'
import { CanvasTexture, Mesh } from 'three'

interface ROI {
  x: number
  y: number
  w: number
  h: number
  tissue: number
}

interface SlideData {
  id: string
  index: number
  name: string
  thumbnail_url?: string
  rois: ROI[]
}

interface Props {
  slides: SlideData[]
  activeSlideIndex?: number
  onSlideClick?: (i: number) => void
}

const TEX_SIZE = 512

function buildSlideTexture(slide: SlideData, index: number, total: number): CanvasTexture {
  const canvas = document.createElement('canvas')
  canvas.width = TEX_SIZE
  canvas.height = TEX_SIZE
  const ctx = canvas.getContext('2d')!

  ctx.fillStyle = 'hsl(25, 20%, 85%)'
  ctx.fillRect(0, 0, TEX_SIZE, TEX_SIZE)

  const grain = ctx.createImageData(TEX_SIZE, TEX_SIZE)
  for (let i = 0; i < grain.data.length; i += 4) {
    const n = (Math.random() - 0.5) * 18
    grain.data[i] = 217 + n
    grain.data[i + 1] = 200 + n
    grain.data[i + 2] = 188 + n
    grain.data[i + 3] = 28
  }
  ctx.putImageData(grain, 0, 0)

  const vignette = ctx.createRadialGradient(
    TEX_SIZE / 2,
    TEX_SIZE / 2,
    TEX_SIZE * 0.25,
    TEX_SIZE / 2,
    TEX_SIZE / 2,
    TEX_SIZE * 0.7,
  )
  vignette.addColorStop(0, 'rgba(0,0,0,0)')
  vignette.addColorStop(1, 'rgba(0,0,0,0.35)')
  ctx.fillStyle = vignette
  ctx.fillRect(0, 0, TEX_SIZE, TEX_SIZE)

  ctx.fillStyle = 'rgba(139, 26, 26, 0.55)'
  ctx.strokeStyle = 'rgba(139, 26, 26, 0.9)'
  ctx.lineWidth = 2
  for (const roi of slide.rois) {
    const rx = roi.x * TEX_SIZE
    const ry = roi.y * TEX_SIZE
    const rw = roi.w * TEX_SIZE
    const rh = roi.h * TEX_SIZE
    ctx.fillRect(rx, ry, rw, rh)
    ctx.strokeRect(rx, ry, rw, rh)
  }

  ctx.font = '14px ui-monospace, monospace'
  ctx.fillStyle = '#ffffff'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  for (const roi of slide.rois) {
    const cx = (roi.x + roi.w / 2) * TEX_SIZE
    const cy = (roi.y + roi.h / 2) * TEX_SIZE
    ctx.fillText(`T:${Math.round(roi.tissue * 100)}%`, cx, cy)
  }

  const t = total > 1 ? index / (total - 1) : 0
  const hue = 30 + t * 180
  ctx.save()
  ctx.globalAlpha = 0.15
  ctx.fillStyle = `hsl(${hue}, 60%, 50%)`
  ctx.fillRect(0, 0, TEX_SIZE, TEX_SIZE)
  ctx.restore()

  const tex = new CanvasTexture(canvas)
  tex.needsUpdate = true
  return tex
}

interface SlidePlaneProps {
  slide: SlideData
  index: number
  total: number
  isActive: boolean
  onClick?: (i: number) => void
}

function SlidePlane({ slide, index, total, isActive, onClick }: SlidePlaneProps) {
  const meshRef = useRef<Mesh>(null)
  const texture = useMemo(() => buildSlideTexture(slide, index, total), [slide, index, total])

  useEffect(() => {
    return () => {
      texture.dispose()
    }
  }, [texture])

  useFrame((_, delta) => {
    const m = meshRef.current
    if (!m) return
    const target = isActive ? 1.0 : 0.92
    const k = 1 - Math.exp(-delta * 8)
    m.scale.x += (target - m.scale.x) * k
    m.scale.y += (target - m.scale.y) * k
    m.scale.z += (target - m.scale.z) * k
  })

  const handleClick = useCallback(
    (e: ThreeEvent<MouseEvent>) => {
      e.stopPropagation()
      onClick?.(index)
    },
    [index, onClick],
  )

  return (
    <mesh
      ref={meshRef}
      position={[0, index * -0.05, index * -1.2]}
      rotation={[-0.05, 0, 0]}
      onClick={handleClick}
    >
      <planeGeometry args={[4, 3]} />
      <meshBasicMaterial map={texture} transparent opacity={isActive ? 1 : 0.85} />
    </mesh>
  )
}

interface SlideStackProps {
  slides: SlideData[]
  activeIndex: number
  onSlideClick?: (i: number) => void
}

function SlideStack({ slides, activeIndex, onSlideClick }: SlideStackProps) {
  return (
    <>
      <ambientLight intensity={0.8} />
      {slides.map((slide, i) => (
        <SlidePlane
          key={slide.id}
          slide={slide}
          index={i}
          total={slides.length}
          isActive={i === activeIndex}
          onClick={onSlideClick}
        />
      ))}
    </>
  )
}

interface SlideHUDProps {
  current: number
  total: number
  name: string
}

function SlideHUD({ current, total, name }: SlideHUDProps) {
  return (
    <Html
      fullscreen
      style={{ pointerEvents: 'none' }}
      zIndexRange={[10, 0]}
    >
      <div
        style={{
          position: 'absolute',
          bottom: 16,
          left: 0,
          right: 0,
          display: 'flex',
          justifyContent: 'center',
          fontFamily: 'ui-monospace, SFMono-Regular, monospace',
          fontSize: 13,
          color: '#f5b400',
          letterSpacing: '0.05em',
          textShadow: '0 0 6px rgba(0,0,0,0.8)',
        }}
      >
        Lame {current + 1} / {total} — {name}
      </div>
    </Html>
  )
}

export default function VolumeViewer({ slides, activeSlideIndex = 0, onSlideClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [internalIndex, setInternalIndex] = useState(activeSlideIndex)

  useEffect(() => {
    setInternalIndex(activeSlideIndex)
  }, [activeSlideIndex])

  const clampIndex = useCallback(
    (i: number) => Math.max(0, Math.min(slides.length - 1, i)),
    [slides.length],
  )

  const handleSlideClick = useCallback(
    (i: number) => {
      const next = clampIndex(i)
      setInternalIndex(next)
      onSlideClick?.(next)
    },
    [clampIndex, onSlideClick],
  )

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
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [clampIndex, onSlideClick, slides.length])

  const active = slides[internalIndex]

  return (
    <div ref={containerRef} style={{ width: '100%', height: '100%', background: '#05080F' }}>
      <Canvas camera={{ position: [0, 2, 8], fov: 45 }} style={{ background: '#05080F' }}>
        <CameraControls makeDefault />
        <SlideStack
          slides={slides}
          activeIndex={internalIndex}
          onSlideClick={handleSlideClick}
        />
        {active && (
          <SlideHUD current={internalIndex} total={slides.length} name={active.name} />
        )}
      </Canvas>
    </div>
  )
}
