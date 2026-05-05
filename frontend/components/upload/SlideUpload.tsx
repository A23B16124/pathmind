
"use client"
import { useCallback, useState } from "react"
import { Slide } from "@/lib/types"

interface Props {
  onSlides: (slides: Slide[]) => void
  onAnalyze: () => void
  onLoadDemo?: () => void
  isRunning: boolean
  slides: Slide[]
}

function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function SlideUpload({ onSlides, onAnalyze, onLoadDemo, isRunning, slides }: Props) {
  const [isDragging, setIsDragging] = useState(false)

  const handleFiles = useCallback((files: FileList | null) => {
    if (!files) return
    const newSlides: Slide[] = Array.from(files).map((f, i) => ({
      id: `slide-${Date.now()}-${i}`,
      name: f.name,
      size: f.size,
      status: "ready" as const,
    }))
    onSlides(newSlides)
  }, [onSlides])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    handleFiles(e.dataTransfer.files)
  }, [handleFiles])

  return (
    <div className="flex flex-col h-full bg-[var(--surface)] border-r border-[var(--border)]">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[var(--border)]">
        <div className="flex items-baseline gap-2">
          <span className="text-sm font-bold tracking-tight text-[var(--accent)]">PathMind</span>
          <span className="text-[10px] font-mono text-[var(--muted)] tracking-widest uppercase">v0.1</span>
        </div>
        <p className="text-[10px] text-[var(--muted)] mt-0.5">Pathology Co-Pilot</p>
      </div>

      {/* Drop zone */}
      <div
        className={`mx-3 mt-3 rounded border-2 border-dashed transition-all duration-200 cursor-pointer flex flex-col items-center justify-center py-6 px-3 gap-2 ${
          isDragging
            ? "border-[var(--accent)] bg-[var(--accent)]/5"
            : "border-[var(--border-2)] bg-[var(--surface-2)] hover:border-[var(--accent)]/40"
        }`}
        onDrop={onDrop}
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
        onDragLeave={() => setIsDragging(false)}
        onClick={() => document.getElementById("file-input")?.click()}
      >
        <div className="w-8 h-8 rounded border border-[var(--border-2)] flex items-center justify-center text-[var(--muted)]">
          <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
            <path d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M12 4v12M8 8l4-4 4 4"/>
          </svg>
        </div>
        <p className="text-[11px] text-[var(--muted)] text-center">
          Drop WSI slides<br/>
          <span className="text-[var(--muted-2)]">.svs .tiff .ndpi .qptiff</span>
        </p>
        <input id="file-input" type="file" multiple accept=".svs,.tiff,.tif,.ndpi,.qptiff" className="hidden"
          onChange={(e) => handleFiles(e.target.files)} />
      </div>

      {onLoadDemo && (
        <button
          onClick={onLoadDemo}
          disabled={isRunning}
          className="mx-3 mt-2 text-[10px] font-mono py-1.5 rounded border border-[var(--accent)]/40 text-[var(--accent)] hover:bg-[var(--accent)]/5 disabled:opacity-30 disabled:cursor-not-allowed tracking-widest uppercase"
        >
          Demo case — Mr. Dubois
        </button>
      )}

      {/* Slide list */}
      <div className="flex-1 overflow-y-auto px-3 mt-2 space-y-1">
        {slides.map((slide, i) => (
          <div key={slide.id} className="flex items-center gap-2 px-2 py-1.5 rounded bg-[var(--surface-2)] border border-[var(--border)]">
            <span className="text-[10px] font-mono text-[var(--accent)] w-4 text-right flex-shrink-0">{String(i + 1).padStart(2, "0")}</span>
            <span className="text-[11px] text-[var(--text)] truncate flex-1">{slide.name}</span>
            <span className="text-[10px] font-mono text-[var(--muted)] flex-shrink-0">{formatSize(slide.size)}</span>
          </div>
        ))}
      </div>

      {/* Analyze button */}
      <div className="flex-shrink-0 p-3 border-t border-[var(--border)]">
        {slides.length > 0 && (
          <p className="text-[10px] font-mono text-[var(--muted)] mb-2 text-center whitespace-nowrap">
            {slides.length} slide{slides.length > 1 ? "s" : ""} loaded
          </p>
        )}
        <button
          disabled={slides.length === 0 || isRunning}
          onClick={onAnalyze}
          className="w-full py-2.5 rounded text-sm font-bold tracking-wide transition-all duration-200 disabled:opacity-30 disabled:cursor-not-allowed"
          style={{
            background: slides.length > 0 && !isRunning
              ? "linear-gradient(135deg, var(--accent-dim), var(--accent))"
              : "var(--border)",
            color: slides.length > 0 && !isRunning ? "#05080F" : "var(--muted)",
            boxShadow: slides.length > 0 && !isRunning ? "0 0 20px var(--accent)/30" : "none",
          }}
        >
          {isRunning ? "Running..." : "Analyze"}
        </button>
      </div>
    </div>
  )
}
