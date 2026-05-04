
"use client"
export const dynamic = "force-dynamic"
import { useState, useCallback, useEffect, useRef } from "react"
import dynamicImport from "next/dynamic"
import { Slide, AgentState, WSEvent, Report, DemoCase } from "@/lib/types"
import { SlideUpload } from "@/components/upload/SlideUpload"
import { AgentPanel } from "@/components/agents/AgentPanel"
import { ReportPanel } from "@/components/report/ReportPanel"
import { connectStream, startAnalysis } from "@/lib/ws"
import { DEMO_DUBOIS, demoSlides } from "@/lib/demo"

const WSIViewer = dynamicImport(
  () => import("@/components/viewer/WSIViewer").then((m) => m.WSIViewer),
  { ssr: false }
)

const MOCK_OVERLAYS = [
  { x: 0.18, y: 0.22, w: 0.16, h: 0.12, color: "#3b82f6", label: "Zone infiltrante" },
  { x: 0.55, y: 0.18, w: 0.10, h: 0.09, color: "#f59e0b", label: "Marge" },
  { x: 0.30, y: 0.55, w: 0.14, h: 0.11, color: "#10b981", label: "Grade III" },
  { x: 0.62, y: 0.62, w: 0.09, h: 0.08, color: "#ef4444", label: "Ki-67+" },
]

const INITIAL_AGENTS: AgentState[] = [
  { name: "tile-triage", label: "Tile Triage", status: "pending", messages: [] },
  { name: "histopathologist", label: "Histopathologist", status: "pending", messages: [] },
  { name: "cross-slide-aggregator", label: "Cross-Slide Aggregator", status: "pending", messages: [] },
  { name: "literature-hunter", label: "Literature Hunter", status: "pending", messages: [] },
  { name: "differential-diagnostician", label: "Differential Dx", status: "pending", messages: [] },
  { name: "quality-control", label: "Quality Control", status: "pending", messages: [] },
  { name: "report-writer", label: "Report Writer", status: "pending", messages: [] },
]

export default function Home() {
  const [slides, setSlides] = useState<Slide[]>([])
  const [agents, setAgents] = useState<AgentState[]>(INITIAL_AGENTS)
  const [isRunning, setIsRunning] = useState(false)
  const [vramPct, setVramPct] = useState(0.06)
  const [report, setReport] = useState<Report | null>(null)
  const [activeCase, setActiveCase] = useState<DemoCase | null>(null)
  const [debugStatus, setDebugStatus] = useState<string[]>([])
  const stopRef = useRef<(() => void) | null>(null)

  const pushDebug = useCallback((line: string) => {
    setDebugStatus((prev) => [...prev, line].slice(-6))
  }, [])

  useEffect(() => () => stopRef.current?.(), [])

  const onEvent = useCallback((event: WSEvent) => {
    pushDebug(`WS event: ${event.type} ${event.agent}`)
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
    if (event.type === "analysis_complete") {
      setIsRunning(false)
      if (event.report) setReport(event.report)
    }
  }, [pushDebug])

  const handleAnalyze = useCallback(async () => {
    if (slides.length === 0) return
    setDebugStatus([])
    setIsRunning(true)
    setReport(null)
    setAgents(INITIAL_AGENTS)
    setVramPct(0.06)

    const caseId = activeCase?.case_id ?? `case-${Date.now()}`
    const patientId = activeCase?.patient_id ?? "anonymous"
    const slidePaths = slides.map((s) => s.path ?? s.name)

    pushDebug("POST /api/analyze...")
    try {
      await startAnalysis({
        case_id: caseId,
        patient_id: patientId,
        slide_paths: slidePaths,
        clinical_data: activeCase
          ? { age: activeCase.age, context: activeCase.clinical_context }
          : undefined,
      })
      pushDebug(`POST OK case_id=${caseId}`)
    } catch (e) {
      pushDebug(`POST ERREUR: ${e instanceof Error ? e.message : String(e)}`)
      console.warn("startAnalysis failed, mock stream will run anyway", e)
    }

    pushDebug("WS connecting...")
    stopRef.current?.()
    stopRef.current = connectStream(caseId, onEvent)
  }, [slides, activeCase, onEvent, pushDebug])

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
    <div className="flex h-screen w-screen overflow-hidden">
      <div className="w-64 flex-shrink-0">
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
            {slides[0]?.name ?? "Aucune lame chargee"}
          </span>
          {activeCase && (
            <span className="text-[10px] font-mono text-[var(--accent)] truncate ml-2">
              | {activeCase.patient_label}
            </span>
          )}
          {isRunning && (
            <span className="ml-auto flex items-center gap-1.5 text-[10px] font-mono text-[var(--running)]">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--running)] agent-running inline-block" />
              Analyse en cours
            </span>
          )}
          {!isRunning && report && (
            <button
              onClick={() => setReport(report)}
              className="ml-auto text-[10px] font-mono px-2 py-0.5 rounded border border-[var(--accent)]/40 text-[var(--accent)] hover:bg-[var(--accent)]/5"
            >
              Voir rapport
            </button>
          )}
        </div>
        {activeCase && (
          <div className="px-4 py-2 border-b border-[var(--border)] bg-[var(--surface-2)] text-[11px] text-[var(--muted)] leading-snug">
            <span className="text-[9px] font-mono text-[var(--accent)] tracking-widest uppercase mr-2">Contexte</span>
            {activeCase.clinical_context}
          </div>
        )}
        <div className="flex-1 min-h-0">
          <WSIViewer
            slideId={slides[0]?.name ?? "Aucune lame"}
            className="w-full h-full"
            overlays={isRunning || report ? MOCK_OVERLAYS : []}
          />
        </div>
      </div>

      <div className="w-80 flex-shrink-0">
        <AgentPanel agents={agents} vramPct={vramPct} isRunning={isRunning} />
      </div>

      {report && (
        <ReportPanel
          report={report}
          patientLabel={activeCase?.patient_label}
          onClose={() => setReport(null)}
        />
      )}

      {debugStatus.length > 0 && (
        <div
          className="fixed bottom-2 right-2 z-50 font-mono text-[10px] text-amber-400 border border-amber-400 bg-black/80 p-2 max-w-[400px] pointer-events-none"
        >
          {debugStatus.map((line, i) => (
            <div key={i} className="truncate">{line}</div>
          ))}
        </div>
      )}
    </div>
  )
}
