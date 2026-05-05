"use client"
import { AgentState, Report } from "@/lib/types"

interface Props {
  report: Report | null
  agents: AgentState[]
}

export function DebateTab({ report, agents }: Props) {
  const cap = (report?.cap_report ?? {}) as Record<string, unknown>
  const rounds = (cap.debate_rounds as Array<Record<string, unknown>> | undefined) ?? []
  const summary = report?.debate_summary ?? (cap.debate_summary as string | undefined)

  const histoA = agents.find((a) => a.name === "histopathologist-a")
  const histoB = agents.find((a) => a.name === "histopathologist-b")

  return (
    <div className="px-5 py-4 space-y-4">
      <div>
        <div className="smcaps mb-2">Lectures indépendantes</div>
        <div className="grid grid-cols-2 gap-3">
          <ReaderCard label="Histo-A" model="Qwen2.5-72B-VL" agent={histoA} accent />
          <ReaderCard label="Histo-B" model="Meditron-70B"   agent={histoB} />
        </div>
      </div>

      {summary && (
        <div className="border border-[var(--accent)] bg-[var(--accent-soft)] p-3">
          <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-[var(--accent)] font-semibold mb-1.5">
            Synthèse arbitrée
          </div>
          <div className="text-[13px] leading-[1.5] text-[var(--ink)]">{summary}</div>
        </div>
      )}

      {rounds.length > 0 && (
        <div>
          <div className="smcaps mb-3">Tours de débat ({rounds.length})</div>
          <div className="space-y-2">
            {rounds.map((r, i) => (
              <div key={i} className="border border-[var(--rule)] bg-[var(--paper)] p-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono text-[10px] text-[var(--accent)]">{String(r.agent_id ?? "")}</span>
                  {r.conceded ? (
                    <span className="font-mono text-[9.5px] uppercase tracking-[0.1em] text-[var(--ok)]">concédé</span>
                  ) : (
                    <span className="font-mono text-[9.5px] uppercase tracking-[0.1em] text-[var(--muted)]">argumente</span>
                  )}
                </div>
                <div className="text-[12px] leading-[1.5] text-[var(--ink-soft)]">{String(r.argument ?? "")}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {!summary && rounds.length === 0 && (
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
      <div className="font-mono text-[10px] text-[var(--muted)] mb-2">{model}</div>
      <div className="text-[11.5px] leading-[1.5] text-[var(--ink-soft)] line-clamp-5">
        {last || "—"}
      </div>
    </div>
  )
}
