"use client"
export const dynamic = "force-dynamic"
import { useState, useCallback, useEffect, useRef } from "react"
import dynamicImport from "next/dynamic"
import { Slide, AgentState, WSEvent, Report, DemoCase, ROIOverlay, HistoFindings } from "@/lib/types"
import { SlideUpload } from "@/components/upload/SlideUpload"
import { ClinicalPanel } from "@/components/clinical/ClinicalPanel"
import { NotesTable, useNotes, type Note } from "@/components/clinical/NotesTable"
import { connectStream, startAnalysis } from "@/lib/ws"
import { DEMO_CASES, demoSlides } from "@/lib/demo"
import { GpuPanel } from "@/components/gpu/GpuPanel"
import { BenchmarkCard } from "@/components/gpu/BenchmarkCard"
import type OpenSeadragon from "openseadragon"
import {
  type Shape,
  type ToolKind,
  type PathMindSymbol,
  PATHMIND_SYMBOLS,
} from "@/components/viewer/AnnotationTypes"
const AnnotationCanvas = dynamicImport(
  () => import("@/components/viewer/AnnotationCanvas").then((m) => m.AnnotationCanvas),
  { ssr: false }
)
import { AnnotationToolbar } from "@/components/viewer/AnnotationToolbar"

const WSIViewer = dynamicImport(
  () => import("@/components/viewer/WSIViewer").then((m) => m.WSIViewer),
  { ssr: false }
)

// localStorage persistence for shapes (drawings)
const SHAPES_STORAGE_KEY = "pathmind:shapes:v2"
function loadShapes(): Shape[] {
  if (typeof window === "undefined") return []
  try {
    const raw = window.localStorage.getItem(SHAPES_STORAGE_KEY)
    if (!raw) return []
    return JSON.parse(raw) as Shape[]
  } catch {
    return []
  }
}
function persistShapes(shapes: Shape[]) {
  if (typeof window === "undefined") return
  window.localStorage.setItem(SHAPES_STORAGE_KEY, JSON.stringify(shapes))
}

const VolumeViewer = dynamicImport(
  () => import("@/components/viewer/VolumeViewer"),
  { ssr: false }
)

const ROI_COLORS = ["#6b1d1d", "#8a5a14", "#2f5d3a", "#4a4538", "#6b1d1dcc", "#8a5a14cc"]
const FALLBACK_OVERLAYS: ROIOverlay[] = [
  { x: 0.18, y: 0.22, w: 0.16, h: 0.12, color: "#6b1d1d", label: "ROI 1" },
  { x: 0.55, y: 0.18, w: 0.10, h: 0.09, color: "#8a5a14", label: "ROI 2" },
  { x: 0.30, y: 0.55, w: 0.14, h: 0.11, color: "#2f5d3a", label: "ROI 3" },
]

const INITIAL_AGENTS: AgentState[] = [
  { name: "tile-triage",                label: "Tile-Triage",                  status: "pending", messages: [] },
  { name: "foundation-uni2",            label: "UNI2-h",                       status: "pending", messages: [] },
  { name: "foundation-virchow2",        label: "Virchow2",                     status: "pending", messages: [] },
  { name: "histopathologist-a",         label: "Histo-A",                      status: "pending", messages: [] },
  { name: "histopathologist-b",         label: "Histo-B",                      status: "pending", messages: [] },
  { name: "cross-slide-aggregator",     label: "Cross-slide",                  status: "pending", messages: [] },
  { name: "literature-hunter",          label: "Literature-Hunter",            status: "pending", messages: [] },
  { name: "differential-diagnostician", label: "Differential-Diagnostician",   status: "pending", messages: [] },
  { name: "quality-control",            label: "Quality-Control",              status: "pending", messages: [] },
  { name: "debate-arena",               label: "Debate-Arena",                 status: "pending", messages: [] },
  { name: "report-writer",              label: "Report-Writer",                status: "pending", messages: [] },
]


function RoiPanel({ findings, slideMeta, roiLabel, onClose }: {
  findings: import('@/lib/types').HistoFindings | undefined
  slideMeta?: import('@/lib/types').HistoFindings
  roiLabel: string
  onClose: () => void
}) {
  const roiId = roiLabel.split(' ')[0] || roiLabel
  if (!findings) {
    return (
      <div className="absolute right-0 top-0 h-full w-[340px] z-20 flex flex-col bg-zinc-950 border-l border-zinc-800">
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 shrink-0">
          <div>
            <div className="text-xs font-mono text-zinc-400 uppercase tracking-widest">ROI</div>
            <div className="text-sm font-semibold text-zinc-100 font-mono">{roiId}</div>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200 transition-colors p-1" aria-label="Fermer">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          </button>
        </div>
        <div className="flex-1 flex items-center justify-center px-6 text-center">
          <div className="space-y-2">
            <div className="inline-block w-4 h-4 border-2 border-zinc-700 border-t-zinc-300 rounded-full animate-spin"></div>
            <div className="text-xs font-mono text-zinc-400 uppercase tracking-widest">Histo-A en cours</div>
            <div className="text-[11px] text-zinc-500">Findings dispo dès que Histo-A finit cette lame.</div>
          </div>
        </div>
      </div>
    )
  }
  const slideId = findings.slide_id ?? '—'
  const grade = findings.sbr_grade
  const mitotic = findings.mitotic_count_per_10hpf
  const necro = findings.necrosis_percent
  const lvi = findings.lymphovascular_invasion
  const pni = findings.perineural_invasion
  const conf = findings.confidence
  const tissues = findings.tissue_types ?? []
  const kf = findings.key_findings ?? []
  const pattern = findings.dominant_pattern

  const flagColor = (val?: string) => {
    if (!val) return 'text-zinc-500'
    const v = val.toLowerCase()
    if (v === 'present') return 'text-red-400'
    if (v === 'absent') return 'text-green-400'
    return 'text-yellow-400'
  }

  return (
    <div className="absolute right-0 top-0 h-full w-[340px] z-20 flex flex-col bg-zinc-950 border-l border-zinc-800 overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 shrink-0">
        <div>
          <div className="text-xs font-mono text-zinc-400 uppercase tracking-widest">ROI</div>
          <div className="text-sm font-semibold text-zinc-100 font-mono">{roiId}</div>
        </div>
        <button
          onClick={onClose}
          className="text-zinc-500 hover:text-zinc-200 transition-colors p-1"
          aria-label="Fermer"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
        </button>
      </div>

      <div className="px-4 py-4 space-y-5 text-sm">
        {tissues.length > 0 && (
          <div>
            <div className="text-[10px] font-mono uppercase tracking-widest text-zinc-500 mb-2">Tissu</div>
            <div className="flex flex-wrap gap-1.5">
              {tissues.map((t, i) => (
                <span key={i} className="px-2 py-0.5 rounded bg-zinc-800 text-zinc-200 text-xs font-mono">{t}</span>
              ))}
            </div>
          </div>
        )}

        {pattern && (
          <div>
            <div className="text-[10px] font-mono uppercase tracking-widest text-zinc-500 mb-1">Architecture</div>
            <div className="text-zinc-300 text-xs leading-relaxed">{pattern}</div>
          </div>
        )}

        {(grade || mitotic != null || necro != null) && (
          <div>
            <div className="text-[10px] font-mono uppercase tracking-widest text-zinc-500 mb-2">Grade</div>
            <div className="flex gap-4 text-xs font-mono">
              {grade && <span className="text-zinc-100">SBR <span className="text-amber-300 font-semibold">{grade}</span></span>}
              {mitotic != null && <span className="text-zinc-300">Mitoses <span className="text-zinc-100">{mitotic}</span><span className="text-zinc-500">/10HPF</span></span>}
              {necro != null && necro > 0 && <span className="text-zinc-300">Necrose <span className="text-zinc-100">{necro}</span><span className="text-zinc-500">%</span></span>}
            </div>
          </div>
        )}

        {(lvi || pni) && (
          <div>
            <div className="text-[10px] font-mono uppercase tracking-widest text-zinc-500 mb-2">Invasion</div>
            <div className="flex gap-4 text-xs font-mono">
              {lvi && <span>LVI <span className={flagColor(lvi)}>{lvi}</span></span>}
              {pni && <span>PNI <span className={flagColor(pni)}>{pni}</span></span>}
            </div>
          </div>
        )}

        {kf.length > 0 && (
          <div>
            <div className="text-[10px] font-mono uppercase tracking-widest text-zinc-500 mb-2">Findings</div>
            <ul className="space-y-1.5">
              {kf.map((f, i) => (
                <li key={i} className="flex gap-2 text-zinc-300 text-xs leading-relaxed">
                  <span className="text-zinc-600 shrink-0 mt-0.5">—</span>
                  <span>{f}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {slideMeta && slideMeta.dominant_pattern && (
          <div className="pt-3 border-t border-zinc-800/80">
            <div className="text-[10px] font-mono uppercase tracking-widest text-zinc-500 mb-1.5">Synthese lame</div>
            <div className="text-[11px] text-zinc-400 leading-relaxed">{slideMeta.dominant_pattern}</div>
          </div>
        )}

        {conf != null && (
          <div className="pt-2 border-t border-zinc-800">
            <div className="flex items-center justify-between text-xs font-mono">
              <span className="text-zinc-500">Confiance Histo-A</span>
              <span className="text-zinc-200">{(conf * 100).toFixed(0)}%</span>
            </div>
            <div className="mt-1.5 h-1 bg-zinc-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-zinc-400 rounded-full transition-all"
                style={{ width: `${(conf * 100).toFixed(0)}%` }}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default function Home() {
  const [slides, setSlides] = useState<Slide[]>([])
  const [agents, setAgents] = useState<AgentState[]>(INITIAL_AGENTS)
  const [isRunning, setIsRunning] = useState(false)
  const [report, setReport] = useState<Report | null>(null)
  const [activeCase, setActiveCase] = useState<DemoCase | null>(null)
  const [overlaysBySlide, setOverlaysBySlide] = useState<Record<number, ROIOverlay[]>>({})
  const [histoFindingsBySlide, setHistoFindingsBySlide] = useState<Record<number, Record<string, HistoFindings>>>({})
  const [selectedRoi, setSelectedRoi] = useState<{ roiIndex: number; label: string } | null>(null)
  const [viewMode, setViewMode] = useState<"2d" | "3d">("2d")
  const [activeSlideIndex, setActiveSlideIndex] = useState<number>(0)
  const [activeVolumeSlide, setActiveVolumeSlide] = useState<number>(0)
  const [boardMode, setBoardMode] = useState<boolean>(false)
  const [pinMode, setPinMode] = useState<boolean>(false)
  const [pendingPin, setPendingPin] = useState<{ x: number; y: number } | null>(null)
  const [pinDraft, setPinDraft] = useState("")
  const stopRef = useRef<(() => void) | null>(null)

  // Annotation board state
  const [tool, setTool] = useState<ToolKind>("select")
  const [annotColor, setAnnotColor] = useState<string>("#ffea00")
  const [strokeWidth, setStrokeWidth] = useState<number>(2.5)
  const [selectedSymbol, setSelectedSymbol] = useState<PathMindSymbol | null>(null)
  const [shapes, setShapes] = useState<Shape[]>([])
  const [osdViewer, setOsdViewer] = useState<OpenSeadragon.Viewer | null>(null)

  useEffect(() => {
    setShapes(loadShapes())
  }, [])

  const caseId = activeCase?.case_id
  const { notes, add: addNote, update: updateNote, remove: removeNote } = useNotes(caseId)

  const addShape = useCallback((s: Shape) => {
    setShapes((prev) => {
      const next = [...prev, s]
      persistShapes(next)
      return next
    })
  }, [])

  const removeShape = useCallback((id: string) => {
    setShapes((prev) => {
      const next = prev.filter((s) => s.id !== id)
      persistShapes(next)
      return next
    })
  }, [])

  const undoLastShape = useCallback(() => {
    setShapes((prev) => {
      if (!caseId) return prev
      const idx = [...prev]
        .reverse()
        .findIndex((s) => s.caseId === caseId && s.slideIndex === activeSlideIndex)
      if (idx === -1) return prev
      const realIdx = prev.length - 1 - idx
      const next = [...prev.slice(0, realIdx), ...prev.slice(realIdx + 1)]
      persistShapes(next)
      return next
    })
  }, [caseId, activeSlideIndex])

  const clearSlideShapes = useCallback(() => {
    setShapes((prev) => {
      if (!caseId) return prev
      const next = prev.filter((s) => !(s.caseId === caseId && s.slideIndex === activeSlideIndex))
      persistShapes(next)
      return next
    })
  }, [caseId, activeSlideIndex])

  const handleViewerReady = useCallback((v: OpenSeadragon.Viewer | null) => {
    setOsdViewer(v)
  }, [])

  useEffect(() => () => stopRef.current?.(), [])

  const onEvent = useCallback((event: WSEvent) => {
    setAgents((prev) =>
      prev.map((a) => {
        if (a.name !== event.agent) return a
        if (event.type === "agent_start") return { ...a, status: "running" }
        if (event.type === "agent_message" && event.message)
          return { ...a, messages: [...a.messages, event.message] }
        if (event.type === "agent_done")
          return { ...a, status: "done", confidence: event.confidence, messages: event.message ? [...a.messages, event.message] : a.messages }
        if (event.type === "agent_error")
          return { ...a, status: "error", messages: event.message ? [...a.messages, event.message] : a.messages }
        return a
      })
    )
    if (event.type === "agent_done" && event.agent === "tile-triage" && event.rois && event.rois.length > 0) {
      const colored = event.rois.map((r, i) => ({ ...r, color: r.color ?? ROI_COLORS[i % ROI_COLORS.length], roiIndex: i }))
      const slideIdx = event.slide ?? 0
      setOverlaysBySlide((prev) => {
        const next = { ...prev, [slideIdx]: colored }
        return next
      })
    }
    if (event.type === "agent_done" && event.agent === "histopathologist-a" && event.message) {
      const slideIdx = event.slide ?? 0
      let raw = event.message.trim()
      const fence = raw.match(/```(?:json)?\s*([\s\S]*?)```/)
      if (fence) raw = fence[1].trim()
      const first = raw.indexOf("{"); const last = raw.lastIndexOf("}")
      if (first >= 0 && last > first) raw = raw.slice(first, last + 1)
      try {
        const parsed = JSON.parse(raw) as { per_roi?: HistoFindings[]; slide_summary?: string; key_findings?: string[]; confidence?: number; slide_id?: string } & HistoFindings
        const byRoi: Record<string, HistoFindings> = {}
        const slideLevel: HistoFindings = {
          slide_id: parsed.slide_id,
          key_findings: parsed.key_findings,
          confidence: parsed.confidence,
          dominant_pattern: parsed.slide_summary,
        }
        if (Array.isArray(parsed.per_roi) && parsed.per_roi.length > 0) {
          for (const entry of parsed.per_roi) {
            const rid = (entry?.roi_id ?? "").toString()
            if (rid) byRoi[rid] = entry
          }
        } else {
          byRoi["__slide__"] = parsed as HistoFindings
        }
        byRoi["__slide__"] = slideLevel
        setHistoFindingsBySlide(prev => ({ ...prev, [slideIdx]: byRoi }))
      } catch (e) {
        console.warn("[Histo-A] JSON parse failed for slide", slideIdx, "raw[:200]:", raw.slice(0, 200))
        setHistoFindingsBySlide(prev => ({
          ...prev,
          [slideIdx]: { __slide__: { key_findings: [event.message ?? ""], confidence: event.confidence } }
        }))
      }
    }
    if (event.type === "analysis_complete") {
      setIsRunning(false)
      if (event.report) setReport(event.report)
    }
  }, [])

  const handleAnalyze = useCallback(async () => {
    if (slides.length === 0) return
    setIsRunning(true)
    setReport(null)
    setAgents(INITIAL_AGENTS)
    setOverlaysBySlide({})
    setHistoFindingsBySlide({})
    setSelectedRoi(null)

    const cId = activeCase?.case_id ?? `case-${Date.now()}`
    const patientId = activeCase?.patient_id ?? "anonymous"
    const slidePaths = slides.map((s) => s.path ?? s.name)

    try {
      await startAnalysis({
        case_id: cId,
        patient_id: patientId,
        slide_paths: slidePaths,
        clinical_data: activeCase
          ? {
              age: activeCase.age,
              sex: activeCase.sex,
              site: activeCase.site,
              sample_type: activeCase.sample_type,
              prior_history: activeCase.prior_history,
              context: activeCase.clinical_context,
            }
          : undefined,
      })
    } catch (e) {
      console.warn("startAnalysis failed, mock stream will run anyway", e)
    }

    stopRef.current?.()
    stopRef.current = connectStream(cId, onEvent)
  }, [slides, activeCase, onEvent])

  const handleLoadDemo = useCallback((demo: DemoCase) => {
    stopRef.current?.()
    stopRef.current = null
    setIsRunning(false)
    setActiveCase(demo)
    setSlides(demoSlides(demo))
    setReport(null)
    setAgents(INITIAL_AGENTS)
    setOverlaysBySlide({})
    setHistoFindingsBySlide({})
    setSelectedRoi(null)
    setActiveSlideIndex(0)
    setActiveVolumeSlide(0)
  }, [])

  const handleSetSlides = useCallback((s: Slide[]) => {
    stopRef.current?.()
    stopRef.current = null
    setIsRunning(false)
    setReport(null)
    setAgents(INITIAL_AGENTS)
    setSlides(s)
    setActiveCase(null)
    setOverlaysBySlide({})
    setHistoFindingsBySlide({})
    setSelectedRoi(null)
    setActiveSlideIndex(0)
  }, [])

  const handleViewerClick = useCallback(
    (xNorm: number, yNorm: number) => {
      if (!pinMode) return
      setPendingPin({ x: xNorm, y: yNorm })
    },
    [pinMode]
  )

  const handleConfirmPin = useCallback(() => {
    if (!pendingPin || !caseId || !pinDraft.trim()) return
    addNote({
      caseId,
      slideIndex: activeSlideIndex,
      slideName: slides[activeSlideIndex]?.name ?? `Lame ${activeSlideIndex + 1}`,
      pinX: pendingPin.x,
      pinY: pendingPin.y,
      text: pinDraft.trim(),
      author: "Praticien",
      category: "observation",
    })
    setPendingPin(null)
    setPinDraft("")
    setPinMode(false)
  }, [pendingPin, caseId, pinDraft, activeSlideIndex, slides, addNote])

  const handleCancelPin = useCallback(() => {
    setPendingPin(null)
    setPinDraft("")
  }, [])

  const handleJumpToPin = useCallback(
    (note: Note) => {
      if (note.slideIndex !== activeSlideIndex) {
        setActiveSlideIndex(note.slideIndex)
      }
      const heroSection = document.getElementById("hero-viewer")
      if (heroSection) {
        heroSection.scrollIntoView({ behavior: "smooth", block: "start" })
      }
    },
    [activeSlideIndex]
  )

  const slideOverlays = overlaysBySlide[activeSlideIndex] ?? []
  const liveOverlays = slideOverlays.length > 0
    ? slideOverlays
    : (isRunning || report ? FALLBACK_OVERLAYS : [])

  const slideName = slides[activeSlideIndex]?.name ?? slides[0]?.name ?? "Aucune lame"
  const pinsForSlide = notes.filter(
    (n) => n.slideIndex === activeSlideIndex && n.pinX != null && n.pinY != null
  )

  return (
    <div className="min-h-screen w-full bg-[var(--paper)] text-[var(--ink)]">
      {/* ── Sticky top bar ── */}
      <header className="sticky top-0 z-40 flex items-stretch border-b border-[var(--rule-strong)] bg-[var(--paper)] h-[56px]">
        <div className="w-[280px] flex items-center gap-2.5 px-[18px] border-r border-[var(--rule-strong)]">
          <div className="w-7 h-7 border border-[var(--ink)] grid place-items-center font-serif italic font-semibold text-[var(--accent)]">
            P
          </div>
          <div className="font-serif text-[18px] font-semibold tracking-[-0.01em]">
            PathMind <span className="font-mono text-[10px] text-[var(--muted)] ml-1">v0.3</span>
          </div>
        </div>
        <div className="flex-1 flex items-center gap-3.5 px-[22px] border-r border-[var(--rule-strong)] min-w-0">
          <span className="text-[12px] text-[var(--ink-soft)]">Service</span>
          <span className="text-[var(--muted)]">/</span>
          <span className="text-[12px] text-[var(--ink-soft)]">Anatomopathologie</span>
          <span className="text-[var(--muted)]">/</span>
          <span className="text-[12px] text-[var(--ink-soft)]">File de lecture</span>
          <span className="text-[var(--muted)]">/</span>
          <span className="text-[12px] text-[var(--ink)] font-medium truncate">
            {activeCase?.patient_label ?? (slides[0]?.name ?? "Aucun cas chargé")}
          </span>
        </div>
        <div className="flex items-center gap-2.5 px-[18px]">
          <span className="font-mono text-[11px] border border-[var(--rule)] bg-[var(--paper-2)] px-2.5 py-1 inline-flex items-center gap-1.5">
            <span className={`w-1.5 h-1.5 rounded-full ${isRunning ? "bg-[var(--accent)] agent-running" : "bg-[var(--ok)]"}`} />
            Qwen2.5-72B-VL · Meditron-70B
          </span>
          <GpuPanel />
        </div>
      </header>

      {/* ── HERO : full-width slide viewer ── */}
      <section
        id="hero-viewer"
        className="relative w-full bg-[#1a1815] overflow-hidden"
        style={{ height: "calc(100vh - 56px)" }}
      >
        {/* Top toolbar */}
        <div className="absolute top-3 left-3 right-3 z-10 flex justify-between items-start gap-3 pointer-events-none">
          <div className="bg-[var(--paper)]/95 border border-[var(--rule-strong)] px-3.5 py-2 flex gap-3.5 items-center pointer-events-auto">
            <span className="font-mono text-[11px] text-[var(--muted)]">
              SP · {slides.length > 0 ? `${activeSlideIndex + 1}/${slides.length}` : "—"}
            </span>
            <span className="font-serif text-[14px] font-semibold truncate max-w-[260px]">
              {slideName}
            </span>
            <span className="text-[11px] text-[var(--ink-soft)] border-l border-[var(--rule)] pl-3.5">
              HES · 40× · 0,25 µm/px
            </span>
          </div>

          <div className="flex gap-2 pointer-events-auto">
            {/* Board mode master toggle — default OFF (pure zoom/pan) */}
            <button
              type="button"
              onClick={() => {
                const next = !boardMode
                setBoardMode(next)
                if (!next) {
                  setTool("select")
                  setPinMode(false)
                  setPendingPin(null)
                  setPinDraft("")
                }
              }}
              disabled={!caseId}
              className={`h-8 px-3 text-xs font-mono uppercase tracking-widest border ${
                boardMode
                  ? "bg-[var(--accent)] text-[var(--paper)] border-[var(--accent)]"
                  : "bg-[var(--paper)]/95 text-[var(--ink-soft)] border-[var(--rule-strong)] hover:bg-[var(--paper-2)]"
              } disabled:opacity-40 disabled:cursor-not-allowed`}
              title={caseId ? (boardMode ? "Cliquez pour revenir en mode zoom" : "Activer le tableau d'annotations") : "Sélectionnez un cas d'abord"}
            >
              {boardMode ? "Tableau ON" : "Activer le tableau"}
            </button>

            {/* Pin sub-toggle — only available when board is ON */}
            {boardMode && (
              <button
                type="button"
                onClick={() => {
                  setPinMode((v) => !v)
                  setPendingPin(null)
                  setPinDraft("")
                }}
                disabled={!caseId}
                className={`h-8 px-3 text-xs font-mono uppercase tracking-widest border ${
                  pinMode
                    ? "bg-[var(--accent)] text-[var(--paper)] border-[var(--accent)]"
                    : "bg-[var(--paper)]/95 text-[var(--ink-soft)] border-[var(--rule-strong)] hover:bg-[var(--paper-2)]"
                } disabled:opacity-40 disabled:cursor-not-allowed`}
                title="Cliquez sur la lame pour épingler une note"
              >
                {pinMode ? "Épingle ON" : "Épingler"}
              </button>
            )}

            {slides.length >= 2 && (
              <div className="flex">
                <button
                  type="button"
                  onClick={() => setViewMode("2d")}
                  className={`h-8 px-3 text-xs font-mono uppercase tracking-widest border border-[var(--rule-strong)] ${
                    viewMode === "2d"
                      ? "bg-[var(--accent)] text-black"
                      : "bg-[var(--surface-2)] text-[var(--muted)]"
                  }`}
                >
                  Vue 2D
                </button>
                <button
                  type="button"
                  onClick={() => setViewMode("3d")}
                  className={`h-8 px-3 text-xs font-mono uppercase tracking-widest border border-l-0 border-[var(--rule-strong)] ${
                    viewMode === "3d"
                      ? "bg-[var(--accent)] text-black"
                      : "bg-[var(--surface-2)] text-[var(--muted)]"
                  }`}
                >
                  Volume 3D
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Slide selector */}
        {viewMode === "2d" && slides.length > 1 && (
          <div className="absolute top-[60px] left-3 right-3 z-10 flex justify-center pointer-events-none">
            <div className="bg-[var(--paper)]/95 border border-[var(--rule-strong)] px-1.5 py-1.5 flex gap-1 pointer-events-auto">
              {slides.map((s, i) => {
                const isActive = i === activeSlideIndex
                const hasROIs = (overlaysBySlide[i]?.length ?? 0) > 0
                const slidePinCount = notes.filter((n) => n.slideIndex === i).length
                return (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => setActiveSlideIndex(i)}
                    title={s.name}
                    className={`h-7 px-3 text-[11px] font-mono uppercase tracking-widest border ${
                      isActive
                        ? "bg-[var(--accent)] text-black border-[var(--accent)]"
                        : "bg-[var(--surface-2)] text-[var(--muted)] border-[var(--rule-strong)] hover:text-[var(--ink)]"
                    }`}
                  >
                    SP {i + 1}
                    {hasROIs && (
                      <span className={`ml-2 inline-block w-1.5 h-1.5 rounded-full ${isActive ? "bg-black/40" : "bg-[var(--accent)]"}`} />
                    )}
                    {slidePinCount > 0 && (
                      <span className={`ml-1.5 text-[9px] ${isActive ? "text-black/60" : "text-[var(--ink-soft)]"}`}>
                        ·{slidePinCount}
                      </span>
                    )}
                  </button>
                )
              })}
            </div>
          </div>
        )}

        {/* Annotation toolbar (floating bottom-center) */}
        {viewMode === "2d" && caseId && boardMode && (
          <div className="absolute bottom-5 left-1/2 -translate-x-1/2 z-20 pointer-events-auto">
            <AnnotationToolbar
              tool={tool}
              setTool={setTool}
              color={annotColor}
              setColor={setAnnotColor}
              strokeWidth={strokeWidth}
              setStrokeWidth={setStrokeWidth}
              selectedSymbol={selectedSymbol}
              setSelectedSymbol={setSelectedSymbol}
              shapeCount={shapes.filter((s) => s.caseId === caseId && s.slideIndex === activeSlideIndex).length}
              onUndo={undoLastShape}
              onClear={clearSlideShapes}
              disabled={!osdViewer}
            />
          </div>
        )}

        {/* Pin mode hint banner */}
        {pinMode && !pendingPin && (
          <div className="absolute top-[110px] left-1/2 -translate-x-1/2 z-20 bg-[var(--accent)] text-[var(--paper)] px-4 py-2 border border-[var(--accent)] pointer-events-none">
            <div className="font-mono text-[11px] uppercase tracking-widest flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-[var(--paper)] animate-pulse" />
              Cliquez sur la zone à épingler
            </div>
          </div>
        )}

        <div className="absolute inset-0 flex">
          {viewMode === "2d" ? (
            <div className="relative flex-1 h-full">
              <WSIViewer
                slideId={slides[activeSlideIndex]?.name ?? slides[0]?.name ?? "Aucune lame"}
                slidePath={slides[activeSlideIndex]?.path ?? slides[0]?.path}
                className="w-full h-full"
                overlays={liveOverlays}
                onRoiClick={(roiIndex, label) => setSelectedRoi({ roiIndex, label })}
                onViewerReady={handleViewerReady}
              />

              {/* Annotation canvas — drawings, shapes, measure, symbols */}
              <div className="annotation-canvas-host absolute inset-0">
                <AnnotationCanvas
                  viewer={osdViewer}
                  caseId={caseId}
                  slideIndex={activeSlideIndex}
                  tool={tool}
                  color={annotColor}
                  strokeWidth={strokeWidth}
                  selectedSymbol={selectedSymbol}
                  shapes={shapes.filter((s) => s.caseId === caseId)}
                  micronsPerPixel={0.25}
                  onAddShape={addShape}
                  onRemoveShape={removeShape}
                />
              </div>

              {/* Pin overlay layer (existing notes + pending) */}
              <div
                className={`absolute inset-0 z-10 ${pinMode ? "cursor-crosshair" : "pointer-events-none"}`}
                onClick={(e) => {
                  if (!pinMode) return
                  const rect = (e.currentTarget as HTMLDivElement).getBoundingClientRect()
                  const x = (e.clientX - rect.left) / rect.width
                  const y = (e.clientY - rect.top) / rect.height
                  handleViewerClick(x, y)
                }}
              >
                {pinsForSlide.map((n) => (
                  <div
                    key={n.id}
                    className="absolute pointer-events-auto group"
                    style={{
                      left: `${(n.pinX ?? 0) * 100}%`,
                      top: `${(n.pinY ?? 0) * 100}%`,
                      transform: "translate(-50%, -100%)",
                    }}
                    title={n.text}
                  >
                    <div className="relative">
                      <div className="w-6 h-6 rounded-full bg-[var(--accent)] border-2 border-[var(--paper)] shadow-lg flex items-center justify-center">
                        <span className="font-mono text-[10px] font-bold text-[var(--paper)]">
                          {notes.indexOf(n) + 1}
                        </span>
                      </div>
                      <div className="w-0.5 h-3 bg-[var(--accent)] mx-auto" />
                      <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover:block bg-[var(--ink)] text-[var(--paper)] text-[11px] px-2 py-1 whitespace-nowrap max-w-[260px] truncate font-serif z-30">
                        {n.text}
                      </div>
                    </div>
                  </div>
                ))}
                {pendingPin && (
                  <div
                    className="absolute pointer-events-auto"
                    style={{
                      left: `${pendingPin.x * 100}%`,
                      top: `${pendingPin.y * 100}%`,
                      transform: "translate(-50%, -100%)",
                    }}
                  >
                    <div className="w-6 h-6 rounded-full bg-[var(--warn)] border-2 border-[var(--paper)] shadow-lg animate-pulse" />
                    <div className="w-0.5 h-3 bg-[var(--warn)] mx-auto" />
                  </div>
                )}
              </div>

              {/* Pending pin composer */}
              {pendingPin && (
                <div className="absolute z-30 bottom-6 left-1/2 -translate-x-1/2 w-[420px] bg-[var(--paper)] border border-[var(--rule-strong)] shadow-2xl">
                  <div className="px-4 py-2.5 border-b border-[var(--rule-strong)] flex items-center justify-between bg-[var(--paper-2)]">
                    <div className="smcaps">Note épinglée — {slideName}</div>
                    <button
                      type="button"
                      onClick={handleCancelPin}
                      className="text-[var(--muted)] hover:text-[var(--ink)] text-sm"
                    >
                      ×
                    </button>
                  </div>
                  <textarea
                    value={pinDraft}
                    onChange={(e) => setPinDraft(e.target.value)}
                    placeholder="Décrivez votre observation à ce point précis..."
                    rows={3}
                    autoFocus
                    className="w-full resize-none bg-[var(--paper)] px-4 py-2.5 text-[13px] font-serif text-[var(--ink)] placeholder:text-[var(--muted)] focus:outline-none"
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                        e.preventDefault()
                        handleConfirmPin()
                      }
                      if (e.key === "Escape") handleCancelPin()
                    }}
                  />
                  <div className="px-4 py-2 border-t border-[var(--rule-strong)] flex justify-between items-center bg-[var(--paper-2)]">
                    <span className="font-mono text-[10px] text-[var(--muted)]">⌘+Entrée pour valider</span>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={handleCancelPin}
                        className="h-7 px-3 text-[10px] font-mono uppercase tracking-widest border border-[var(--rule-strong)] text-[var(--muted)]"
                      >
                        Annuler
                      </button>
                      <button
                        type="button"
                        onClick={handleConfirmPin}
                        disabled={!pinDraft.trim()}
                        className="h-7 px-3 text-[10px] font-mono uppercase tracking-widest bg-[var(--accent)] text-[var(--paper)] disabled:opacity-30"
                      >
                        Épingler
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {selectedRoi && (() => {
                const roiId = selectedRoi.label.split(" ")[0] || ""
                const slideMap = histoFindingsBySlide[activeSlideIndex]
                const f = slideMap?.[roiId] ?? slideMap?.["__slide__"]
                const slideMeta = slideMap?.["__slide__"]
                return (
                  <RoiPanel
                    findings={f}
                    slideMeta={slideMeta}
                    roiLabel={selectedRoi.label}
                    onClose={() => setSelectedRoi(null)}
                  />
                )
              })()}
            </div>
          ) : (
            <div className="relative flex-1 h-full">
              <VolumeViewer
                caseId={activeCase?.case_id}
                slides={
                  activeCase
                    ? undefined
                    : slides.map((s, i) => ({
                        id: s.id,
                        index: i,
                        name: s.name,
                        rois: FALLBACK_OVERLAYS.slice(0, 4).map((r) => ({
                          x: r.x,
                          y: r.y,
                          w: r.w,
                          h: r.h,
                          tissue: r.tissue ?? 0.7,
                        })),
                      }))
                }
                activeSlideIndex={activeVolumeSlide}
                onSlideClick={(i) => setActiveVolumeSlide(i)}
              />
            </div>
          )}
        </div>

        {/* Scroll-down hint */}
        <button
          type="button"
          onClick={() => {
            const el = document.getElementById("workspace-grid")
            if (el) el.scrollIntoView({ behavior: "smooth", block: "start" })
          }}
          className="absolute bottom-6 right-6 z-20 w-10 h-10 rounded-full bg-[var(--ink)] text-[var(--paper)] border border-[var(--paper)] hover:bg-[var(--accent)] transition-colors grid place-items-center shadow-xl"
          title="Voir l'espace de travail"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M3 5l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </section>

      {/* ── WORKSPACE : 3-col grid below the hero, scrollable ── */}
      <section
        id="workspace-grid"
        className="grid grid-cols-[280px_1fr_400px] border-t border-[var(--rule-strong)] min-h-[600px]"
      >
        {/* Left rail : cases / upload */}
        <div className="border-r border-[var(--rule-strong)] bg-[var(--paper)]">
          <SlideUpload
            slides={slides}
            onSlides={handleSetSlides}
            onAnalyze={handleAnalyze}
            onLoadDemo={handleLoadDemo}
            demoCases={DEMO_CASES}
            activeCaseId={activeCase?.case_id}
            isRunning={isRunning}
          />
        </div>

        {/* Middle : patient context + interactive notes table */}
        <div className="bg-[var(--paper-2)]/30 p-5 space-y-5">
          {/* Patient context panel */}
          {activeCase ? (
            <div className="border border-[var(--rule-strong)] bg-[var(--paper)]">
              <div className="px-5 py-4 border-b border-[var(--rule-strong)] flex items-baseline justify-between gap-4">
                <div>
                  <div className="smcaps">Contexte patient</div>
                  <div className="font-serif text-[18px] font-semibold tracking-tight">
                    {activeCase.patient_label ?? activeCase.patient_id}
                  </div>
                </div>
                <div className="font-mono text-[10px] uppercase tracking-widest text-[var(--muted)] text-right">
                  {activeCase.case_id}
                </div>
              </div>

              <dl className="grid grid-cols-2 gap-x-6 gap-y-3 px-5 py-4 text-[13px] border-b border-[var(--rule-strong)]">
                {activeCase.age != null && activeCase.age > 0 && (
                  <div>
                    <dt className="font-mono text-[10px] uppercase tracking-widest text-[var(--muted)] mb-0.5">Âge</dt>
                    <dd className="text-[var(--ink)]">{activeCase.age} ans</dd>
                  </div>
                )}
                {activeCase.sex && (
                  <div>
                    <dt className="font-mono text-[10px] uppercase tracking-widest text-[var(--muted)] mb-0.5">Sexe</dt>
                    <dd className="text-[var(--ink)]">{activeCase.sex === "M" ? "Masculin" : activeCase.sex === "F" ? "Féminin" : activeCase.sex}</dd>
                  </div>
                )}
                {activeCase.site && (
                  <div>
                    <dt className="font-mono text-[10px] uppercase tracking-widest text-[var(--muted)] mb-0.5">Site</dt>
                    <dd className="text-[var(--ink)]">{activeCase.site}</dd>
                  </div>
                )}
                {activeCase.sample_type && (
                  <div>
                    <dt className="font-mono text-[10px] uppercase tracking-widest text-[var(--muted)] mb-0.5">Prélèvement</dt>
                    <dd className="text-[var(--ink)]">{activeCase.sample_type}</dd>
                  </div>
                )}
                {activeCase.prior_history && (
                  <div className="col-span-2">
                    <dt className="font-mono text-[10px] uppercase tracking-widest text-[var(--muted)] mb-0.5">Antécédents</dt>
                    <dd className="text-[var(--ink-soft)] font-serif italic">{activeCase.prior_history}</dd>
                  </div>
                )}
              </dl>

              {activeCase.clinical_context && (
                <div className="px-5 py-4">
                  <div className="font-mono text-[10px] uppercase tracking-widest text-[var(--accent)] mb-2">
                    Demande clinique
                  </div>
                  <p className="font-serif text-[14px] leading-relaxed text-[var(--ink)]">
                    {activeCase.clinical_context}
                  </p>
                </div>
              )}
            </div>
          ) : (
            <div className="border border-[var(--rule-strong)] bg-[var(--paper)] px-5 py-6">
              <div className="smcaps mb-1.5">Contexte patient</div>
              <div className="text-sm text-[var(--muted)] font-serif italic">
                Sélectionnez un cas pour afficher le contexte clinique.
              </div>
            </div>
          )}

          <NotesTable
            caseId={caseId}
            caseLabel={activeCase?.patient_label}
            slideIndex={activeSlideIndex}
            slideName={slideName}
            notes={notes}
            onAdd={addNote}
            onUpdate={updateNote}
            onRemove={removeNote}
            onJumpToPin={handleJumpToPin}
          />

          {/* Benchmark card */}
          {!isRunning && (
            <div className="mt-5">
              <BenchmarkCard />
            </div>
          )}
        </div>

        {/* Right rail : clinical panel (agents + report) */}
        <div className="border-l border-[var(--rule-strong)] bg-[var(--paper)]">
          <ClinicalPanel
            agents={agents}
            isRunning={isRunning}
            report={report}
            patientLabel={activeCase?.patient_label}
          />
        </div>
      </section>
    </div>
  )
}
