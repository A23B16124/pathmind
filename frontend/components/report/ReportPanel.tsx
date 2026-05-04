"use client"
import { Report } from "@/lib/types"

interface Props {
  report: Report | null
  patientLabel?: string
  onClose: () => void
  onExport?: () => void
}

export function ReportPanel({ report, patientLabel, onClose, onExport }: Props) {
  if (!report) return null

  const conf = Math.round((report.confidence ?? 0) * 100)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-6">
      <div className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-lg border border-[var(--accent)]/40 bg-[var(--surface)] shadow-2xl">
        <div className="sticky top-0 z-10 flex items-center justify-between px-5 py-3 border-b border-[var(--border)] bg-[var(--surface)]">
          <div className="flex items-baseline gap-3">
            <span className="text-[10px] font-mono text-[var(--accent)] tracking-widest uppercase">Rapport CAP</span>
            <span className="text-sm font-bold text-[var(--text)]">{patientLabel ?? "Patient"}</span>
          </div>
          <button
            onClick={onClose}
            className="text-[var(--muted)] hover:text-[var(--text)] text-xl leading-none"
            aria-label="Fermer"
          >
            ×
          </button>
        </div>

        <div className="px-5 py-4 space-y-4">
          <Section label="Diagnostic principal">
            <p className="text-base font-medium text-[var(--text)] leading-snug">
              {report.diagnosis}
            </p>
            <div className="flex items-center gap-3 mt-2">
              <ConfidenceBar pct={conf} />
              <span className="text-xs font-mono text-[var(--accent)] flex-shrink-0">{conf}%</span>
            </div>
          </Section>

          {report.grade && (
            <Section label="Grade">
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-mono border border-[var(--accent)]/40 text-[var(--accent)] bg-[var(--accent)]/5">
                Grade {report.grade}
              </span>
            </Section>
          )}

          {report.margins && (
            <Section label="Marges">
              <span className="text-sm font-mono text-[var(--text)]">{report.margins}</span>
            </Section>
          )}

          {report.biomarkers && report.biomarkers.length > 0 && (
            <Section label="Biomarqueurs">
              <div className="flex flex-wrap gap-1.5">
                {report.biomarkers.map((b, i) => (
                  <span key={i} className="text-[11px] font-mono px-2 py-0.5 rounded border border-[var(--border)] bg-[var(--surface-2)] text-[var(--text)]">
                    {b}
                  </span>
                ))}
              </div>
            </Section>
          )}

          {report.similarCases !== undefined && (
            <Section label="Litterature">
              <p className="text-xs text-[var(--muted)]">
                <span className="text-[var(--text)] font-mono">{report.similarCases}</span> cas similaires identifies dans la base TCGA + PubMed
              </p>
            </Section>
          )}

          {report.rawText && !report.diagnosis && (
            <Section label="Sortie brute">
              <pre className="text-xs font-mono text-[var(--muted)] whitespace-pre-wrap">
                {report.rawText}
              </pre>
            </Section>
          )}
        </div>

        <div className="sticky bottom-0 flex items-center justify-end gap-2 px-5 py-3 border-t border-[var(--border)] bg-[var(--surface)]">
          {onExport && (
            <button
              onClick={onExport}
              className="text-[11px] font-mono px-3 py-1.5 rounded border border-[var(--border)] hover:border-[var(--accent)]/40 text-[var(--text)]"
            >
              Exporter PDF
            </button>
          )}
          <button
            onClick={onClose}
            className="text-[11px] font-mono px-3 py-1.5 rounded bg-[var(--accent)] text-[var(--surface)] hover:opacity-90"
          >
            Fermer
          </button>
        </div>
      </div>
    </div>
  )
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[9px] font-mono text-[var(--muted)] tracking-widest uppercase mb-1.5">
        {label}
      </div>
      {children}
    </div>
  )
}

function ConfidenceBar({ pct }: { pct: number }) {
  return (
    <div className="flex-1 h-1 bg-[var(--surface-2)] rounded-full overflow-hidden">
      <div
        className="h-full bg-[var(--accent)] transition-all duration-700"
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}
