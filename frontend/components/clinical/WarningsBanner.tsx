"use client"
import { useState } from "react"
import { ReportWarning } from "@/lib/types"

interface Props {
  warnings: ReportWarning[]
}

const SEV_CFG: Record<ReportWarning["severity"], { color: string; bg: string; label: string }> = {
  danger: { color: "var(--accent)", bg: "var(--accent-soft)", label: "À VÉRIFIER" },
  warn:   { color: "var(--warn)",   bg: "rgba(138, 90, 20, 0.10)", label: "Attention" },
  info:   { color: "var(--muted)",  bg: "var(--paper-2)", label: "Info" },
}

export function WarningsBanner({ warnings }: Props) {
  const [open, setOpen] = useState(true)
  if (!warnings || warnings.length === 0) return null

  const counts = warnings.reduce<Record<string, number>>((acc, w) => {
    acc[w.severity] = (acc[w.severity] ?? 0) + 1
    return acc
  }, {})

  const dangerCount = counts.danger ?? 0
  const warnCount = counts.warn ?? 0

  return (
    <div className="border-b border-[var(--rule)]">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-2.5 bg-[var(--accent-soft)] hover:bg-[var(--accent-soft)]/80 transition-colors text-left"
      >
        <div className="flex items-center gap-2.5">
          <svg className="w-4 h-4 text-[var(--accent)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="M12 9v4M12 17h.01" strokeLinecap="round" />
            <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
          </svg>
          <div>
            <div className="font-serif text-[13px] font-semibold text-[var(--ink)]">
              Audit anti-hallucination — {warnings.length} signalement{warnings.length > 1 ? "s" : ""}
            </div>
            <div className="font-mono text-[10px] text-[var(--ink-soft)]">
              {dangerCount > 0 && <span className="text-[var(--accent)] font-semibold">{dangerCount} critique{dangerCount > 1 ? "s" : ""}</span>}
              {dangerCount > 0 && warnCount > 0 && <span className="text-[var(--muted)]"> · </span>}
              {warnCount > 0 && <span className="text-[var(--warn)]">{warnCount} avertissement{warnCount > 1 ? "s" : ""}</span>}
              {dangerCount === 0 && warnCount === 0 && <span>{warnings.length} info</span>}
            </div>
          </div>
        </div>
        <svg
          className={`w-3.5 h-3.5 text-[var(--ink-soft)] transition-transform ${open ? "rotate-180" : ""}`}
          viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
        >
          <path d="M6 9l6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open && (
        <div className="bg-[var(--paper)] divide-y divide-[var(--rule)]">
          {warnings.map((w, i) => {
            const cfg = SEV_CFG[w.severity] ?? SEV_CFG.info
            return (
              <div
                key={`${w.code}-${i}`}
                className="px-4 py-2.5 flex items-start gap-2.5"
                style={{ borderLeft: `3px solid ${cfg.color}` }}
              >
                <span
                  className="font-mono text-[9px] uppercase tracking-[0.12em] font-semibold flex-shrink-0 mt-0.5 px-1.5 py-0.5"
                  style={{ color: cfg.color, background: cfg.bg }}
                >
                  {cfg.label}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-[12px] leading-[1.45] text-[var(--ink)]">{w.message}</div>
                  {w.evidence && (
                    <div className="font-mono text-[10px] text-[var(--ink-soft)] mt-0.5 truncate">
                      → {w.evidence}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
          <div className="px-4 py-2 font-mono text-[9.5px] text-[var(--muted)] italic">
            Ces signalements sont produits automatiquement par l'audit post-pipeline.
            Ils ne remplacent pas la relecture par l'anatomopathologiste.
          </div>
        </div>
      )}
    </div>
  )
}
