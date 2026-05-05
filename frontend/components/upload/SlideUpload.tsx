"use client"
import { useCallback, useState } from "react"
import { DemoCase, Slide } from "@/lib/types"

interface Props {
  onSlides: (slides: Slide[]) => void
  onAnalyze: () => void
  onLoadDemo?: (demo: DemoCase) => void
  demoCases?: DemoCase[]
  activeCaseId?: string
  isRunning: boolean
  slides: Slide[]
}

function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} ko`
  return `${(bytes / 1024 / 1024).toFixed(1)} Mo`
}

export function SlideUpload({
  onSlides, onAnalyze, onLoadDemo, demoCases, activeCaseId, isRunning, slides,
}: Props) {
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
    <div className="flex flex-col h-full bg-[var(--paper)] border-r border-[var(--rule-strong)]">
      {/* Brand header */}
      <div className="px-4 py-3.5 border-b border-[var(--rule-strong)]">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 border border-[var(--ink)] grid place-items-center font-serif italic font-semibold text-[var(--accent)]">
            P
          </div>
          <div className="leading-tight">
            <div className="font-serif text-[18px] font-semibold tracking-[-0.01em]">PathMind</div>
            <div className="font-mono text-[10px] text-[var(--muted)]">v0.2 · clinique</div>
          </div>
        </div>
      </div>

      {/* Section title */}
      <div className="px-4 pt-4 pb-2 border-b border-[var(--rule)] flex items-baseline justify-between">
        <span className="font-serif text-[15px] font-semibold">File de lecture</span>
        <span className="font-mono text-[11px] text-[var(--muted)]">
          {slides.length > 0 ? `${slides.length} lame${slides.length > 1 ? "s" : ""}` : "vide"}
        </span>
      </div>

      {/* Drop zone */}
      <div
        className={`mx-4 mt-3 border border-dashed cursor-pointer flex flex-col items-center justify-center py-5 px-3 gap-2 transition-colors ${
          isDragging
            ? "border-[var(--accent)] bg-[var(--accent-soft)]"
            : "border-[var(--rule-strong)] bg-[var(--paper-2)] hover:border-[var(--accent)]"
        }`}
        onDrop={onDrop}
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
        onDragLeave={() => setIsDragging(false)}
        onClick={() => document.getElementById("file-input")?.click()}
      >
        <div className="w-8 h-8 border border-[var(--rule-strong)] grid place-items-center text-[var(--ink-soft)]">
          <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
            <path d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M12 4v12M8 8l4-4 4 4"/>
          </svg>
        </div>
        <p className="text-[11px] text-[var(--ink-soft)] text-center leading-snug">
          Déposer une lame WSI<br/>
          <span className="font-mono text-[10px] text-[var(--muted)]">.svs · .ndpi · .tiff · .qptiff</span>
        </p>
        <input
          id="file-input" type="file" multiple
          accept=".svs,.tiff,.tif,.ndpi,.qptiff"
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {onLoadDemo && demoCases && demoCases.length > 0 && (
        <div className="mx-4 mt-3">
          <div className="smcaps mb-1.5">Cas démo</div>
          <div className="flex flex-col">
            {demoCases.map((d) => {
              const active = d.case_id === activeCaseId
              return (
                <button
                  key={d.case_id}
                  onClick={() => onLoadDemo(d)}
                  disabled={isRunning}
                  className={`text-left px-2.5 py-2 text-[11px] border-b border-[var(--rule)] last:border-b-0 first:border-t border-x ${
                    active
                      ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--ink)]"
                      : "border-[var(--rule)] hover:bg-[var(--paper-2)] text-[var(--ink-soft)]"
                  } disabled:opacity-40 disabled:cursor-not-allowed transition-colors`}
                >
                  <div className="font-serif text-[12px] font-medium leading-tight">
                    {d.patient_label}
                  </div>
                  <div className="font-mono text-[9.5px] text-[var(--muted)] mt-0.5 truncate">
                    {d.case_id}
                  </div>
                </button>
              )
            })}
          </div>
        </div>
      )}

      {/* Slide list */}
      <div className="flex-1 overflow-y-auto mt-3">
        {slides.map((slide, i) => (
          <div
            key={slide.id}
            className="grid grid-cols-[28px_1fr_auto] items-center gap-2.5 px-4 py-2.5 border-b border-[var(--rule)] hover:bg-[var(--paper-2)]"
          >
            <span className="font-mono text-[10px] text-[var(--accent)] text-right">
              {String(i + 1).padStart(2, "0")}
            </span>
            <span className="font-serif text-[13px] text-[var(--ink)] truncate" title={slide.name}>
              {slide.name}
            </span>
            <span className="font-mono text-[10px] text-[var(--muted)]">{formatSize(slide.size)}</span>
          </div>
        ))}
      </div>

      {/* Analyze button */}
      <div className="flex-shrink-0 p-4 border-t border-[var(--rule-strong)] bg-[var(--paper-2)]">
        <button
          disabled={slides.length === 0 || isRunning}
          onClick={onAnalyze}
          className="w-full py-2.5 text-[12px] font-medium tracking-wide bg-[var(--ink)] text-[var(--paper)] border border-[var(--ink)] hover:bg-[var(--accent)] hover:border-[var(--accent)] disabled:bg-[var(--rule)] disabled:border-[var(--rule)] disabled:text-[var(--muted)] disabled:cursor-not-allowed transition-colors"
        >
          {isRunning ? "Pipeline en cours…" : "Analyser le cas"}
        </button>
      </div>
    </div>
  )
}
