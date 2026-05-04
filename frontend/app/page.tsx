
"use client"
import { useState, useCallback } from "react"
import { Slide, AgentState, WSEvent } from "@/lib/types"
import { SlideUpload } from "@/components/upload/SlideUpload"
import { AgentPanel } from "@/components/agents/AgentPanel"
import { WSIViewer } from "@/components/viewer/WSIViewer"
import { createMockStream } from "@/lib/ws"

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

  const handleAnalyze = useCallback(() => {
    setIsRunning(true)
    setAgents(INITIAL_AGENTS)
    setVramPct(0.06)

    const stop = createMockStream((event: WSEvent) => {
      setAgents(prev => prev.map(a => {
        if (a.name !== event.agent) return a
        if (event.type === "agent_start") return { ...a, status: "running" }
        if (event.type === "agent_message") return { ...a, messages: [...a.messages, event.message ?? ""] }
        if (event.type === "agent_done") return { ...a, status: "done", confidence: event.confidence }
        return a
      }))
      if (event.type === "agent_start") setVramPct(p => Math.min(p + 0.12, 0.89))
      if (event.type === "analysis_complete") setIsRunning(false)
    })

    return stop
  }, [])

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      {/* Left — slide upload */}
      <div className="w-64 flex-shrink-0">
        <SlideUpload
          slides={slides}
          onSlides={setSlides}
          onAnalyze={handleAnalyze}
          isRunning={isRunning}
        />
      </div>

      {/* Center — WSI viewer */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Topbar */}
        <div className="h-10 flex items-center px-4 border-b border-[var(--border)] bg-[var(--surface)] gap-3 flex-shrink-0">
          <span className="text-[10px] font-mono text-[var(--muted)] tracking-widest uppercase">Viewer</span>
          <span className="text-[11px] font-mono text-[var(--text)] truncate">
            {slides[0]?.name ?? "Aucune lame chargee"}
          </span>
          {isRunning && (
            <span className="ml-auto flex items-center gap-1.5 text-[10px] font-mono text-[var(--running)]">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--running)] agent-running inline-block" />
              Analyse en cours
            </span>
          )}
        </div>
        <div className="flex-1 min-h-0">
          <WSIViewer
            slideId={slides[0]?.name ?? "Aucune lame"}
            className="w-full h-full"
          />
        </div>
      </div>

      {/* Right — agent panel */}
      <div className="w-80 flex-shrink-0">
        <AgentPanel agents={agents} vramPct={vramPct} isRunning={isRunning} />
      </div>
    </div>
  )
}
