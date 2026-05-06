"use client"
export const dynamic = "force-dynamic"
import { useState, useCallback, useEffect, useRef } from "react"
import dynamicImport from "next/dynamic"
import { Slide, AgentState, WSEvent, Report, DemoCase, ROIOverlay } from "@/lib/types"
import { SlideUpload } from "@/components/upload/SlideUpload"
import { ClinicalPanel } from "@/components/clinical/ClinicalPanel"
import { connectStream, startAnalysis, fetchCachedReport, replayFromCache } from "@/lib/ws"
import { DEMO_CASES, demoSlides } from "@/lib/demo"

const WSIViewer = dynamicImport(
  () => import("@/components/viewer/WSIViewer").then((m) => m.WSIViewer),
  { ssr: false }
)

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
  { name: "tile-triage",            label: "Tile-Triage",            status: "pending", messages: [] },
  { name: "histopathologist-a",     label: "Histo-A",                status: "pending", messages: [] },
  { name: "histopathologist-b",     label: "Histo-B",                status: "pending", messages: [] },
  { name: "cross-slide-aggregator", label: "Cross-slide",            status: "pending", messages: [] },
  { name: "literature-hunter",      label: "Literature-Hunter",      status: "pending", messages: [] },
  { name: "chief",                  label: "Chief",                  status: "pending", messages: [] },
]

export default function Home() {
  const [slides, setSlides] = useState<Slide[]>([])
  const [agents, setAgents] = useState<AgentState[]>(INITIAL_AGENTS)
  const [isRunning, setIsRunning] = useState(false)
  const [report, setReport] = useState<Report | null>(null)
  const [activeCase, setActiveCase] = useState<DemoCase | null>(null)
  const [overlaysBySlide, setOverlaysBySlide] = useState<Record<number, ROIOverlay[]>>({})
  const [viewMode, setViewMode] = useState<"2d" | "3d">("2d")
  const [activeSlideIndex, setActiveSlideIndex] = useState<number>(0)
  const [activeVolumeSlide, setActiveVolumeSlide] = useState<number>(0)
  const stopRef = useRef<(() => void) | null>(null)

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
      const colored = event.rois.map((r, i) => ({ ...r, color: r.color ?? ROI_COLORS[i % ROI_COLORS.length] }))
      const slideIdx = event.slide ?? 0
      setOverlaysBySlide((prev) => ({ ...prev, [slideIdx]: colored }))
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

    const caseId = activeCase?.case_id ?? `case-${Date.now()}`
    const patientId = activeCase?.patient_id ?? "anonymous"
    const slidePaths = slides.map((s) => s.path ?? s.name)

    // Cache hit → instant replay of the pre-computed report (3s synthetic stream).
    // Cache miss → live pipeline (5–10 min) with WS stream.
    const cached = await fetchCachedReport(caseId)
    if (cached) {
      stopRef.current?.()
      stopRef.current = replayFromCache(cached, onEvent)
      return
    }

    try {
      await startAnalysis({
        case_id: caseId,
        patient_id: patientId,
        slide_paths: slidePaths,
        clinical_data: activeCase
          ? { age: activeCase.age, context: activeCase.clinical_context }
          : undefined,
      })
    } catch (e) {
      console.warn("startAnalysis failed, mock stream will run anyway", e)
    }

    stopRef.current?.()
    stopRef.current = connectStream(caseId, onEvent)
  }, [slides, activeCase, onEvent])

  const handleLoadDemo = useCallback((demo: DemoCase) => {
    setActiveCase(demo)
    setSlides(demoSlides(demo))
    setReport(null)
    setAgents(INITIAL_AGENTS)
    setOverlaysBySlide({})
    setActiveSlideIndex(0)
    setActiveVolumeSlide(0)
  }, [])

  const handleSetSlides = useCallback((s: Slide[]) => {
    setSlides(s)
    setActiveCase(null)
    setOverlaysBySlide({})
    setActiveSlideIndex(0)
  }, [])

  const slideOverlays = overlaysBySlide[activeSlideIndex] ?? []
  const liveOverlays = slideOverlays.length > 0
    ? slideOverlays
    : (isRunning || report ? FALLBACK_OVERLAYS : [])

  return (
    <div className="grid grid-rows-[56px_1fr] grid-cols-[280px_1fr_400px] h-[100dvh] w-screen overflow-hidden">
      {/* ── Top bar ── */}
      <header className="col-span-3 flex items-stretch border-b border-[var(--rule-strong)] bg-[var(--paper)]">
        <div className="w-[280px] flex items-center gap-2.5 px-[18px] border-r border-[var(--rule-strong)]">
          <div className="w-7 h-7 border border-[var(--ink)] grid place-items-center font-serif italic font-semibold text-[var(--accent)]">
            P
          </div>
          <div className="font-serif text-[18px] font-semibold tracking-[-0.01em]">
            PathMind <span className="font-mono text-[10px] text-[var(--muted)] ml-1">v0.2</span>
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
          <span className="font-mono text-[11px] border border-[var(--rule)] bg-[var(--paper-2)] px-2.5 py-1">
            MI300X · 192 Go HBM
          </span>
        </div>
      </header>

      {/* ── Left rail ── */}
      <SlideUpload
        slides={slides}
        onSlides={handleSetSlides}
        onAnalyze={handleAnalyze}
        onLoadDemo={handleLoadDemo}
        demoCases={DEMO_CASES}
        activeCaseId={activeCase?.case_id}
        isRunning={isRunning}
      />

      {/* ── Center: viewer ── */}
      <main className="relative bg-[#1a1815] overflow-hidden">
        <div className="absolute top-3 left-3 right-3 z-10 flex justify-between items-start gap-3 pointer-events-none">
          <div className="bg-[var(--paper)]/95 border border-[var(--rule-strong)] px-3.5 py-2 flex gap-3.5 items-center pointer-events-auto">
            <span className="font-mono text-[11px] text-[var(--muted)]">
              SP · {slides.length > 0 ? `${activeSlideIndex + 1}/${slides.length}` : "—"}
            </span>
            <span className="font-serif text-[14px] font-semibold truncate max-w-[260px]">
              {slides[activeSlideIndex]?.name ?? slides[0]?.name ?? "Pas de lame chargée"}
            </span>
            <span className="text-[11px] text-[var(--ink-soft)] border-l border-[var(--rule)] pl-3.5">
              HES · 40× · 0,25 µm/px
            </span>
          </div>
          {slides.length >= 2 && (
            <div className="flex pointer-events-auto">
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

        {/* Slide selector — only in 2D when the case has multiple slides */}
        {viewMode === "2d" && slides.length > 1 && (
          <div className="absolute top-[60px] left-3 right-3 z-10 flex justify-center pointer-events-none">
            <div className="bg-[var(--paper)]/95 border border-[var(--rule-strong)] px-1.5 py-1.5 flex gap-1 pointer-events-auto">
              {slides.map((s, i) => {
                const isActive = i === activeSlideIndex
                const hasROIs = (overlaysBySlide[i]?.length ?? 0) > 0
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
                  </button>
                )
              })}
            </div>
          </div>
        )}

        <div className="absolute inset-0">
          {viewMode === "2d" ? (
            <WSIViewer
              slideId={slides[activeSlideIndex]?.name ?? slides[0]?.name ?? "Aucune lame"}
              slidePath={slides[activeSlideIndex]?.path ?? slides[0]?.path}
              className="w-full h-full"
              overlays={liveOverlays}
            />
          ) : (
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
          )}
        </div>

        {activeCase && (
          <div className="absolute bottom-3 left-3 right-[200px] z-10 bg-[var(--paper)]/95 border border-[var(--rule-strong)] px-3.5 py-2 pointer-events-auto">
            <span className="font-mono text-[9.5px] uppercase tracking-[0.16em] text-[var(--accent)] mr-2.5">
              Contexte
            </span>
            <span className="text-[12px] text-[var(--ink-soft)]">{activeCase.clinical_context}</span>
          </div>
        )}
      </main>

      {/* ── Right rail: clinical panel ── */}
      <ClinicalPanel
        agents={agents}
        isRunning={isRunning}
        report={report}
        patientLabel={activeCase?.patient_label}
      />
    </div>
  )
}
