
"use client"
export const dynamic = "force-dynamic"
import { useState, useCallback, useEffect, useRef } from "react"
import dynamicImport from "next/dynamic"
import { Slide, AgentState, WSEvent, Report, DemoCase, ROIOverlay } from "@/lib/types"
import { SlideUpload } from "@/components/upload/SlideUpload"
import { AgentPanel } from "@/components/agents/AgentPanel"
import { ReportPanel } from "@/components/report/ReportPanel"
import { connectStream, startAnalysis } from "@/lib/ws"
import { DEMO_DUBOIS, demoSlides } from "@/lib/demo"

const WSIViewer = dynamicImport(
  () => import("@/components/viewer/WSIViewer").then((m) => m.WSIViewer),
  { ssr: false }
)

const ROI_COLORS = ["#3b82f6", "#f59e0b", "#10b981", "#ef4444", "#a855f7", "#06b6d4", "#ec4899", "#84cc16"]
const FALLBACK_OVERLAYS: ROIOverlay[] = [
  { x: 0.18, y: 0.22, w: 0.16, h: 0.12, color: "#3b82f6", label: "ROI 1" },
  { x: 0.55, y: 0.18, w: 0.10, h: 0.09, color: "#f59e0b", label: "ROI 2" },
  { x: 0.30, y: 0.55, w: 0.14, h: 0.11, color: "#10b981", label: "ROI 3" },
]

const INITIAL_AGENTS: AgentState[] = [
  { name: "tile-triage",            label: "Tile Triage",            status: "pending", messages: [] },
  { name: "histopathologist-a",     label: "Histo-A (Qwen 72B)",     status: "pending", messages: [] },
  { name: "histopathologist-b",     label: "Histo-B (Meditron 70B)", status: "pending", messages: [] },
  { name: "cross-slide-aggregator", label: "Cross-Slide Aggregator", status: "pending", messages: [] },
  { name: "literature-hunter",      label: "Literature Hunter",      status: "pending", messages: [] },
  { name: "chief",                  label: "Chief (Arbitrator)",     status: "pending", messages: [] },
]

export default function Home() {
  const [slides, setSlides] = useState<Slide[]>([])
  const [agents, setAgents] = useState<AgentState[]>(INITIAL_AGENTS)
  const [isRunning, setIsRunning] = useState(false)
  const [vramPct, setVramPct] = useState(0.06)
  const [report, setReport] = useState<Report | null>(null)
  const [activeCase, setActiveCase] = useState<DemoCase | null>(null)
  const [overlays, setOverlays] = useState<ROIOverlay[]>([])
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
    if (event.type === "agent_start") setVramPct((p) => Math.min(p + 0.12, 0.89))
    if (event.type === "agent_done" && event.agent === "tile-triage" && event.rois && event.rois.length > 0) {
      const colored = event.rois.map((r, i) => ({ ...r, color: r.color ?? ROI_COLORS[i % ROI_COLORS.length] }))
      setOverlays((prev) => (event.slide === 0 || prev.length === 0 ? colored : [...prev, ...colored]))
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
    setVramPct(0.06)
    setOverlays([])

    const caseId = activeCase?.case_id ?? `case-${Date.now()}`
    const patientId = activeCase?.patient_id ?? "anonymous"
    const slidePaths = slides.map((s) => s.path ?? s.name)

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

  const handleLoadDemo = useCallback(() => {
    const demo = DEMO_DUBOIS
    setActiveCase(demo)
    setSlides(demoSlides(demo))
    setReport(null)
    setAgents(INITIAL_AGENTS)
  }, [])

  const handleSetSlides = useCallback((s: Slide[]) => {
    setSlides(s)
    setActiveCase(null)
  }, [])

  return (
    <div className="flex h-[100dvh] w-screen overflow-hidden">
      <div className="w-64 flex-shrink-0 h-full">
        <SlideUpload
          slides={slides}
          onSlides={handleSetSlides}
          onAnalyze={handleAnalyze}
          onLoadDemo={handleLoadDemo}
          isRunning={isRunning}
        />
      </div>

      <div className="flex-1 flex flex-col min-w-0">
        <div className="h-10 flex items-center px-4 border-b border-[var(--border)] bg-[var(--surface)] gap-3 flex-shrink-0">
          <span className="text-[10px] font-mono text-[var(--muted)] tracking-widest uppercase">Viewer</span>
          <span className="text-[11px] font-mono text-[var(--text)] truncate">
            {slides[0]?.name ?? "No slide loaded"}
          </span>
          {activeCase && (
            <span className="text-[10px] font-mono text-[var(--accent)] truncate ml-2">
              | {activeCase.patient_label}
            </span>
          )}
          {isRunning && (
            <span className="ml-auto flex items-center gap-1.5 text-[10px] font-mono text-[var(--running)]">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--running)] agent-running inline-block" />
              Running
            </span>
          )}
          {!isRunning && report && (
            <button
              onClick={() => setReport(report)}
              className="ml-auto text-[10px] font-mono px-2 py-0.5 rounded border border-[var(--accent)]/40 text-[var(--accent)] hover:bg-[var(--accent)]/5"
            >
              View report
            </button>
          )}
        </div>
        {activeCase && (
          <div className="px-4 py-2 border-b border-[var(--border)] bg-[var(--surface-2)] text-[11px] text-[var(--muted)] leading-snug">
            <span className="text-[9px] font-mono text-[var(--accent)] tracking-widest uppercase mr-2">Context</span>
            {activeCase.clinical_context}
          </div>
        )}
        <div className="flex-1 min-h-0">
          <WSIViewer
            slideId={slides[0]?.name ?? "No slide"}
            className="w-full h-full"
            overlays={overlays.length > 0 ? overlays : (isRunning || report ? FALLBACK_OVERLAYS : [])}
          />
        </div>
      </div>

      <div className="w-80 flex-shrink-0 h-full">
        <AgentPanel agents={agents} vramPct={vramPct} isRunning={isRunning} />
      </div>

      {report && (
        <ReportPanel
          report={report}
          patientLabel={activeCase?.patient_label}
          onClose={() => setReport(null)}
        />
      )}

    </div>
  )
}
