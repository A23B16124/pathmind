"use client"
import { AgentState, Report } from "@/lib/types"

interface Props {
  report: Report | null
  agents: AgentState[]
}

export function DebateTab({ report, agents }: Props) {
  const cap = (report?.cap_report ?? {}) as Record<string, unknown>
  const summary = report?.debate_summary ?? (cap.debate_summary as string | undefined)

  // Live debate stream — events emitted by the backend during the loop.
  const arena = agents.find((a) => a.name === "debate-arena")
  const liveEvents = arena?.messages ?? []

  // Final debate_history from the backend (set when pipeline complete).
  type DebateEntry = {
    round?: number
    agent?: string
    diagnosis?: string
    confidence?: number
    verdict?: string
    challenges?: string[]
    argument?: string
    thinking?: string
    conceded?: boolean
  }
  const history: DebateEntry[] = ((report as unknown as Record<string, unknown>)?.debate_history as DebateEntry[]) || []

  const histoA = agents.find((a) => a.name === "histopathologist-a")
  const histoB = agents.find((a) => a.name === "histopathologist-b")

  // Group history by round
  const rounds = new Map<number, DebateEntry[]>()
  for (const h of history) {
    const r = h.round ?? 0
    if (!rounds.has(r)) rounds.set(r, [])
    rounds.get(r)!.push(h)
  }
  const roundKeys = Array.from(rounds.keys()).sort((a, b) => a - b)

  return (
    <div className="px-5 py-4 space-y-4">
      <div>
        <div className="smcaps mb-2">Lectures indépendantes</div>
        <div className="grid grid-cols-2 gap-3">
          <ReaderCard label="Histo-A" model="Qwen2.5-72B-VL" agent={histoA} accent />
          <ReaderCard label="Histo-B" model="Meditron-70B"   agent={histoB} />
        </div>
      </div>

      {/* LIVE DEBATE STREAM — visible while pipeline runs */}
      {liveEvents.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <span className="smcaps">Débat en direct</span>
            {arena?.status === "running" && (
              <span className="font-mono text-[9.5px] uppercase tracking-[0.1em] text-[var(--accent)] animate-pulse">live</span>
            )}
          </div>
          <div className="space-y-1.5">
            {liveEvents.map((m, i) => {
              const isQC = m.includes("QC verdict") || m.includes("QC ")
              const isDDx = m.includes("DDx ") || m.includes("revising")
              const color = isQC ? "border-amber-600 bg-amber-50/50 dark:bg-amber-950/20"
                          : isDDx ? "border-blue-600 bg-blue-50/50 dark:bg-blue-950/20"
                          : "border-[var(--rule)]"
              const tag = isQC ? "QC" : isDDx ? "DDx" : "—"
              return (
                <div key={i} className={`border-l-2 ${color} pl-2.5 py-1.5 text-[12px] leading-[1.4]`}>
                  <span className="font-mono text-[9.5px] uppercase tracking-[0.1em] text-[var(--muted)] mr-2">{tag}</span>
                  <span className="text-[var(--ink)]">{m}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {summary && (
        <div className="border border-[var(--accent)] bg-[var(--accent-soft)] p-3">
          <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-[var(--accent)] font-semibold mb-1.5">
            Synthèse arbitrée
          </div>
          <div className="text-[13px] leading-[1.5] text-[var(--ink)]">{summary}</div>
        </div>
      )}

      {/* HISTORY by round — shown when pipeline complete */}
      {roundKeys.length > 0 && (
        <div>
          <div className="smcaps mb-3">Tours de débat ({roundKeys.length})</div>
          <div className="space-y-3">
            {roundKeys.map((rn) => (
              <div key={rn} className="border border-[var(--rule-strong)] bg-[var(--paper)] p-3">
                <div className="font-mono text-[11px] uppercase tracking-[0.14em] text-[var(--accent)] font-semibold mb-2">
                  Round {rn}
                </div>
                <div className="space-y-2">
                  {(rounds.get(rn) ?? []).map((entry, i) => {
                    const isQC = entry.agent === "quality-control"
                    return (
                      <div key={i} className={`pl-2 border-l-2 ${isQC ? "border-amber-600" : "border-blue-600"}`}>
                        <div className="flex items-center justify-between mb-0.5">
                          <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-[var(--accent)]">
                            {isQC ? "Quality-Control" : "Differential-Diagnostician"}
                          </span>
                          {entry.confidence !== undefined && (
                            <span className="font-mono text-[10px] text-[var(--ink-soft)]">τ {entry.confidence.toFixed(2)}</span>
                          )}
                        </div>
                        <div className="text-[12px] leading-[1.5] text-[var(--ink-soft)]">{entry.argument}</div>
                        {entry.challenges && entry.challenges.length > 0 && (
                          <ul className="mt-1.5 space-y-0.5">
                            {entry.challenges.map((c, j) => (
                              <li key={j} className="text-[11px] text-[var(--muted)] before:content-['→_'] before:text-[var(--accent)]">{c}</li>
                            ))}
                          </ul>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {!summary && roundKeys.length === 0 && liveEvents.length === 0 && (
        <div className="font-serif italic text-[14px] text-[var(--muted)] leading-relaxed">
          Pas de débat tant que le pipeline n'a pas terminé. Les désaccords entre Histo-A et
          Histo-B (grade, marges, EPN, biomarqueurs) seront tranchés ici par le Chief.
        </div>
      )}
    </div>
  )
}

function ReaderCard({
  label, model, agent, accent,
}: {
  label: string; model: string; agent?: AgentState; accent?: boolean;
}) {
  const last = agent?.messages?.length ? agent.messages[agent.messages.length - 1] : ""
  return (
    <div className={`border ${accent ? "border-[var(--accent)]" : "border-[var(--rule-strong)]"} bg-[var(--paper)] p-3`}>
      <div className="flex items-baseline justify-between mb-1">
        <span className="font-serif text-[14px] font-semibold">{label}</span>
        {agent?.confidence !== undefined && (
          <span className="font-mono text-[11px] text-[var(--ink-soft)]">τ {agent.confidence.toFixed(2)}</span>
        )}
      </div>
      <div className="font-mono text-[10px] uppercase tracking-[0.1em] text-[var(--muted)] mb-1.5">{model}</div>
      <div className="text-[11.5px] leading-[1.5] text-[var(--ink-soft)] line-clamp-4">{last || "En attente..."}</div>
    </div>
  )
}
