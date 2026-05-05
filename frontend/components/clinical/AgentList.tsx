"use client"
import { AgentState, AgentStatus } from "@/lib/types"

const STATUS_CLASS: Record<AgentStatus, { dot: string; right: string }> = {
  pending: { dot: "bg-[var(--rule)]", right: "—" },
  running: { dot: "bg-[var(--running)] agent-running", right: "en cours" },
  done:    { dot: "bg-[var(--ok)]", right: "" },
  error:   { dot: "bg-[var(--accent)]", right: "erreur" },
}

interface Props {
  agents: AgentState[]
  agentLabels: Record<string, { label: string; sub: string }>
  isRunning: boolean
}

export function AgentList({ agents, agentLabels, isRunning }: Props) {
  const doneCount = agents.filter((a) => a.status === "done").length

  return (
    <div className="px-4 py-4 border-b border-[var(--rule)]">
      <div className="flex items-baseline justify-between mb-2.5">
        <span className="smcaps">Pipeline · LangGraph</span>
        <span className="font-mono text-[11px] text-[var(--muted)]">
          {doneCount}/{agents.length} {isRunning ? "· actif" : ""}
        </span>
      </div>

      {agents.map((a, i) => {
        const meta = agentLabels[a.name] ?? { label: a.name, sub: "" }
        const status = STATUS_CLASS[a.status]
        const lastMsg = a.messages.length > 0 ? a.messages[a.messages.length - 1] : ""
        return (
          <div
            key={a.name}
            className={`grid grid-cols-[14px_1fr_auto] gap-2.5 items-center py-2 ${i > 0 ? "border-t border-dotted border-[var(--rule)]" : ""}`}
          >
            <span className={`w-2 h-2 rounded-full ${status.dot}`} />
            <div className="min-w-0">
              <div className="text-[13px] font-medium text-[var(--ink)] truncate">
                {meta.label}
              </div>
              <div className="font-mono text-[10px] text-[var(--muted)] truncate">
                {meta.sub}
                {lastMsg && a.status === "running" ? ` · ${lastMsg.slice(0, 60)}` : ""}
              </div>
            </div>
            <div className="font-mono text-[11px] text-[var(--ink-soft)] text-right">
              {a.confidence !== undefined ? `τ ${a.confidence.toFixed(2)}` : status.right}
            </div>
          </div>
        )
      })}
    </div>
  )
}
