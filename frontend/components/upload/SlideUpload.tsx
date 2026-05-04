'use client'
import { useCallback, useRef, useState } from 'react'
import { Slide } from '@/lib/types'
import { Button } from '@/components/ui/button'

interface Props {
  onSlides: (slides: Slide[]) => void
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

export function SlideUpload({ onSlides }: Props) {
  const [files, setFiles] = useState<File[]>([])
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const addFiles = useCallback((incoming: FileList | File[]) => {
    setFiles((prev) => [...prev, ...Array.from(incoming)])
  }, [])

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault()
      setDragOver(false)
      if (e.dataTransfer.files.length > 0) addFiles(e.dataTransfer.files)
    },
    [addFiles],
  )

  const handleAnalyse = () => {
    const slides: Slide[] = files.map((f, i) => ({
      id: `slide-${Date.now()}-${i}`,
      name: f.name,
      size: f.size,
      status: 'ready',
    }))
    onSlides(slides)
  }

  return (
    <div className="flex flex-col gap-4 p-4 h-full">
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-6 text-center cursor-pointer transition-colors ${
          dragOver ? 'border-blue-500 bg-blue-950/30' : 'border-zinc-700 bg-zinc-900/40 hover:border-zinc-600'
        }`}
      >
        <span className="text-sm font-medium text-zinc-200">Deposer des lames WSI</span>
        <span className="text-xs text-zinc-500">.svs .ndpi .tiff — glisser ou cliquer</span>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".svs,.ndpi,.tiff,.tif,.mrxs"
          className="hidden"
          onChange={(e) => {
            if (e.target.files) addFiles(e.target.files)
          }}
        />
      </div>

      <div className="flex-1 overflow-y-auto space-y-2">
        {files.map((f, i) => (
          <div
            key={`${f.name}-${i}`}
            className="rounded border border-zinc-800 bg-zinc-900 p-2 flex items-center justify-between gap-2"
          >
            <span className="text-xs text-zinc-200 truncate">{f.name}</span>
            <span className="text-xs text-zinc-500 shrink-0">{formatSize(f.size)}</span>
          </div>
        ))}
      </div>

      <Button disabled={files.length === 0} onClick={handleAnalyse} className="w-full">
        Analyser
      </Button>
    </div>
  )
}
