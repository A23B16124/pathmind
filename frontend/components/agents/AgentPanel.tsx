
"use client"
import { useEffect, useRef, useState } from "react"
import { AgentState, AgentStatus } from "@/lib/types"

const AGENT_LABELS: Record<string, string> = {
  "tile-triage": "Tile Triage",
  "foundation-uni2": "UNI2-h",
  "foundation-virchow2": "Virchow2",
  "histopathologist-a": "Histo-A",
  "histopathologist-b": "Histo-B",
  "cross-slide-aggregator": "Cross-Slide Aggregator",
  "literature-hunter": "Literature Hunter",
  "differential-diagnostician": "Differential-Diagnostician",
  "quality-control": "Quality-Control",
  "report-writer": "Report-Writer",
  "debate-arena": "Debate-Arena",
}

const AGENT_MODEL_BADGE: Record<string, string> = {
  "histopathologist-a": "Qwen 72B",
  "histopathologist-b": "Llama-3.3-70B (Groq)",
  "differential-diagnostician": "Qwen 72B",
  "quality-control": "Qwen 72B",
  "report-writer": "Qwen 72B",
}

const STATUS_DOT: Record<AgentStatus, string> = {
  pending: "bg-[var(--muted-2)]",
  running: "bg-[var(--running)] agent-running",
  done: "bg-[var(--done)]",
  error: "bg-[var(--error)]",
}

const STATUS_BORDER: Record<AgentStatus, string> = {
  pending: "border-[var(--border)]",
  running: "border-[var(--running)]/40",
  done: "border-[var(--done)]/30",
  error: "border-[var(--error)]/30",
}

interface Props {
  agents: AgentState[]
  vramPct: number
  isRunning: boolean
}

export function AgentPanel({ agents, vramPct, isRunning }: Props) {
  const vramGb = Math.round(vramPct * 192)
  const doneCount = agents.filter(a => a.status === "done").length

  const [displayed, setDisplayed] = useState<Record<string, string>>({})
  const targetsRef = useRef<Record<string, string>>({})
  const intervalsRef = useRef<Record<string, ReturnType<typeof setInterval>>>({})

  useEffect(() => {
    for (const agent of agents) {
      const latest = agent.messages.length > 0 ? agent.messages[agent.messages.length - 1] : ""
      if (targetsRef.current[agent.name] === latest) continue
      targetsRef.current[agent.name] = latest

      if (intervalsRef.current[agent.name]) {
        clearInterval(intervalsRef.current[agent.name])
        delete intervalsRef.current[agent.name]
      }

      if (!latest) {
        setDisplayed((d) => ({ ...d, [agent.name]: "" }))
        continue
      }

      const words = latest.split(/(\s+)/)
      let i = 0
      setDisplayed((d) => ({ ...d, [agent.name]: "" }))
      const id = setInterval(() => {
        i += 1
        const next = words.slice(0, i).join("")
        setDisplayed((d) => ({ ...d, [agent.name]: next }))
        if (i >= words.length) {
          clearInterval(id)
          delete intervalsRef.current[agent.name]
        }
      }, 60)
      intervalsRef.current[agent.name] = id
    }
  }, [agents])

  useEffect(() => {
    const intervals = intervalsRef.current
    return () => {
      for (const id of Object.values(intervals)) clearInterval(id)
    }
  }, [])

  return (
    <div className="flex flex-col h-full bg-[var(--surface)] border-l border-[var(--border)]">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[var(--border)] flex items-center justify-between gap-2">
        <span className="text-xs font-mono text-[var(--muted)] tracking-widest uppercase whitespace-nowrap">Agents</span>
        <span className="text-xs font-mono text-[var(--accent)] whitespace-nowrap flex-shrink-0">{doneCount}/{agents.length}</span>
      </div>

      {/* VRAM bar */}
      <div className="px-4 py-3 border-b border-[var(--border)] space-y-1.5">
        <div className="flex justify-between items-baseline">
          <span className="text-[10px] font-mono text-[var(--muted)] tracking-widest uppercase">AMD MI300X VRAM</span>
          <span className="text-[11px] font-mono text-[var(--accent)]">{vramGb} <span className="text-[var(--muted)]">/ 192 GB</span></span>
        </div>
        <div className="h-1 bg-[var(--border)] rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-700"
            style={{
              width: `${vramPct * 100}%`,
              background: `linear-gradient(90deg, var(--accent-dim), var(--accent))`,
              boxShadow: vramPct > 0 ? "0 0 8px var(--accent)" : "none",
            }}
          />
        </div>
      </div>

      {/* Agent list */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
        {agents.map((agent, i) => (
          <div
            key={agent.name}
            className={`stagger-in rounded border p-3 transition-all duration-300 ${STATUS_BORDER[agent.status]} bg-[var(--surface-2)]`}
            style={{ animationDelay: `${i * 60}ms` }}
          >
            <div className="flex items-center gap-2 mb-1">
              <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${STATUS_DOT[agent.status]}`} />
              <span className="text-[11px] font-semibold tracking-wide text-[var(--text)] truncate">
                {AGENT_LABELS[agent.name] ?? agent.name}
              </span>
              {AGENT_MODEL_BADGE[agent.name] && (
                <span className="text-[8px] font-mono px-1 py-0 rounded border border-[var(--border)] text-[var(--muted)] flex-shrink-0">
                  {AGENT_MODEL_BADGE[agent.name]}
                </span>
              )}
              {(agent.name === "quality-control" || agent.name === "differential-diagnostician") && agent.messages.some(m => m.includes("challenge") || m.includes("Debate:") || m.includes("QC")) && (
                <span className="text-[8px] font-mono px-1 py-0 rounded border border-amber-500/40 text-amber-400 bg-amber-500/5 flex-shrink-0">
                  DEBATE
                </span>
              )}
            </div>
            {agent.messages.length > 0 && (
              <p className="text-[10px] font-mono text-[var(--muted)] leading-relaxed ml-3.5 line-clamp-3">
                {displayed[agent.name] ?? ""}
                {agent.status === "running" && (
                  <span className="inline-block w-[6px] h-[10px] ml-0.5 align-[-1px] bg-[var(--running)] cursor-blink" />
                )}
              </p>
            )}
            {agent.confidence !== undefined && (
              <div className="mt-1.5 ml-3.5 flex items-center gap-1.5">
                <div className="flex-1 h-0.5 bg-[var(--border)] rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full bg-[var(--done)]"
                    style={{ width: `${agent.confidence * 100}%` }}
                  />
                </div>
                <span className="text-[10px] font-mono text-[var(--done)]">
                  {Math.round(agent.confidence * 100)}%
                </span>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
