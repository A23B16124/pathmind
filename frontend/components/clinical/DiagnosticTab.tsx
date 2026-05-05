"use client"
import { Report } from "@/lib/types"

interface Props {
  report: Report | null
  patientLabel?: string
}

export function DiagnosticTab({ report, patientLabel }: Props) {
  if (!report) {
    return (
      <div className="p-6 font-serif text-[14px] text-[var(--muted)] italic leading-relaxed">
        En attente du diagnostic du Chief. Les ROI extraites par Tile-Triage,
        les lectures Histo-A et Histo-B, puis l'arbitrage final apparaîtront
        ici dès la fin du pipeline.
      </div>
    )
  }

  const cap = (report.cap_report ?? {}) as Record<string, unknown>
  const dx       = report.primary_diagnosis ?? report.diagnosis ?? "Diagnostic indéterminé"
  const icd      = String(cap.icd_o_code ?? report.icd_o_code ?? "—")
  const tnm      = `${cap.pt_stage ?? report.pt_stage ?? "—"} ${cap.pn_stage ?? report.pn_stage ?? ""}`.trim()
  const margin   = String(cap.margin_status ?? report.margin_status ?? "—")
  const pni      = String(cap.perineural_invasion ?? "—")
  const conf     = report.confidence ?? 0
  const findings = (cap.key_findings as string[] | undefined) ?? []
  const recos    = (cap.recommendations as string[] | undefined) ?? report.recommendations ?? []
  const biomarkers = report.biomarkers ?? (cap.biomarkers as string[] | undefined) ?? []

  return (
    <div>
      {/* Disagreement strip */}
      {report.debate_summary && (
        <div className="mx-4 my-4 border border-[var(--accent)] bg-[var(--accent-soft)] p-3">
          <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-[var(--accent)] font-semibold mb-1.5">
            Synthèse du débat
          </div>
          <div className="text-[12px] leading-[1.5] text-[var(--ink)]">
            {report.debate_summary}
          </div>
        </div>
      )}

      {/* Diagnosis block */}
      <div className="px-5 pt-2 pb-6 border-b border-[var(--rule)]">
        <div className="font-mono text-[9.5px] uppercase tracking-[0.16em] text-[var(--muted)] mb-1.5">
          Diagnostic primaire
        </div>
        <h2 className="font-serif text-[22px] font-semibold leading-[1.18] tracking-[-0.012em] mb-1">
          {dx}
        </h2>
        {patientLabel && (
          <div className="text-[12px] italic text-[var(--ink-soft)] mb-4">{patientLabel}</div>
        )}

        <div className="grid grid-cols-2 border border-[var(--rule)] bg-[var(--paper-2)]">
          <Cell k="ICD-O-3"    v={icd} />
          <Cell k="Stade pTNM" v={tnm || "—"} last />
          <Cell k="Marges"     v={margin} bottom />
          <Cell k="Engainement périnerveux" v={pni} bottom last />
        </div>

        {/* Confidence */}
        <div className="mt-4 grid grid-cols-[1fr_auto] gap-3 items-center">
          <div>
            <div className="smcaps mb-1.5">Confiance multi-agents</div>
            <div className="h-[6px] bg-[var(--paper-2)] border border-[var(--rule)] overflow-hidden">
              <div className="h-full bg-[var(--accent)]" style={{ width: `${Math.round(conf * 100)}%` }} />
            </div>
          </div>
          <div className="font-serif text-[18px] font-semibold text-[var(--accent)]">
            {conf.toFixed(2)}<span className="font-mono text-[11px] text-[var(--muted)] ml-1">/1</span>
          </div>
        </div>
      </div>

      {/* Biomarkers */}
      {biomarkers.length > 0 && (
        <div className="px-5 py-4 border-b border-[var(--rule)]">
          <div className="smcaps mb-2">Biomarqueurs recommandés (IHC)</div>
          <div className="flex flex-wrap gap-1.5">
            {biomarkers.map((b) => (
              <span
                key={b}
                className="font-mono text-[11px] px-2 py-0.5 border border-[var(--rule-strong)] text-[var(--ink)] bg-[var(--paper-2)]"
              >
                {b}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Key findings */}
      {findings.length > 0 && (
        <div className="px-5 py-4 border-b border-[var(--rule)]">
          <div className="smcaps mb-3">Constatations clés</div>
          {findings.map((f, i) => (
            <div key={i} className={`grid grid-cols-[24px_1fr] gap-2.5 py-2.5 ${i > 0 ? "border-t border-[var(--rule)]" : ""}`}>
              <div className="font-serif italic text-[14px] text-[var(--accent)] text-right">
                {romanize(i + 1)}.
              </div>
              <div className="text-[12px] leading-[1.5] text-[var(--ink-soft)]">{f}</div>
            </div>
          ))}
        </div>
      )}

      {/* Recommendations */}
      {recos.length > 0 && (
        <div className="px-5 py-4">
          <div className="smcaps mb-3">Recommandations cliniques</div>
          <ul className="space-y-1.5">
            {recos.map((r, i) => (
              <li key={i} className="text-[12px] leading-[1.5] text-[var(--ink)] flex gap-2">
                <span className="text-[var(--accent)] font-mono mt-0.5">›</span>
                <span>{r}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function Cell({ k, v, last, bottom }: { k: string; v: string; last?: boolean; bottom?: boolean }) {
  return (
    <div
      className={`px-3 py-2.5 border-r border-b border-[var(--rule)] ${last ? "border-r-0" : ""} ${bottom ? "border-b-0" : ""}`}
    >
      <div className="font-mono text-[9.5px] uppercase tracking-[0.1em] text-[var(--muted)]">{k}</div>
      <div className="font-serif text-[14px] font-medium mt-0.5 text-[var(--ink)]">{v}</div>
    </div>
  )
}

function romanize(n: number): string {
  return ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"][n - 1] ?? String(n)
}
