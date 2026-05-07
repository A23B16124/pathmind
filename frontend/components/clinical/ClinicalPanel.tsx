"use client"
import { useState } from "react"
import { AgentState, AgentStatus, Report } from "@/lib/types"
import { AgentList } from "./AgentList"
import { DiagnosticTab } from "./DiagnosticTab"
import { LiteratureTab } from "./LiteratureTab"
import { DebateTab } from "./DebateTab"
import { WarningsBanner } from "./WarningsBanner"

const AGENT_LABELS: Record<string, { label: string; sub: string }> = {
  "tile-triage":                { label: "Tile-Triage",                      sub: "tissue mask · Otsu" },
  "foundation-uni2":            { label: "UNI2-h",                           sub: "ViT-G/14 · pathology FM" },
  "foundation-virchow2":        { label: "Virchow2",                         sub: "ViT-H/14 · pathology FM" },
  "histopathologist-a":         { label: "Histo-A · lecture primaire",        sub: "Qwen2.5-72B-VL" },
  "histopathologist-b":         { label: "Histo-B · lecture indépendante",    sub: "Meditron-70B" },
  "cross-slide-aggregator":     { label: "Cross-slide · agrégation",          sub: "map-reduce" },
  "literature-hunter":          { label: "Literature-Hunter",                 sub: "Qdrant · TCGA + PubMed" },
  "differential-diagnostician": { label: "Differential-Diagnostician",        sub: "DDx chaîne de pensée" },
  "quality-control":            { label: "Quality-Control · débat",           sub: "audit critique" },
  "debate-arena":               { label: "Debate-Arena · live",              sub: "DDx ↔ QC rounds" },
  "report-writer":              { label: "Report-Writer",                     sub: "rapport CAP final" },
}

type TabKey = "diagnostic" | "debate" | "literature"

interface Props {
  agents: AgentState[]
  isRunning: boolean
  report: Report | null
  patientLabel?: string
}

export function ClinicalPanel({ agents, isRunning, report, patientLabel }: Props) {
  const [tab, setTab] = useState<TabKey>("diagnostic")

  const tabs: { key: TabKey; label: string }[] = [
    { key: "diagnostic", label: "Diagnostic" },
    { key: "debate", label: "Débat" },
    { key: "literature", label: "Littérature" },
  ]

  const litCount =
    (report?.literature?.used_papers?.length ?? 0) +
    (report?.literature?.suggested_papers?.length ?? 0)

  return (
    <aside className="h-full flex flex-col bg-[var(--paper)] border-l border-[var(--rule-strong)] overflow-hidden">
      {/* Tabs */}
      <div className="flex border-b border-[var(--rule-strong)]">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex-1 py-3.5 px-3 font-serif text-[15px] font-medium border-r border-[var(--rule)] last:border-r-0 transition-colors ${
              tab === t.key
                ? "text-[var(--ink)] bg-[var(--paper-2)] border-b-2 border-b-[var(--accent)] -mb-px"
                : "text-[var(--muted)] hover:text-[var(--ink-soft)]"
            }`}
          >
            {t.label}
            {t.key === "literature" && litCount > 0 && (
              <span className="ml-1.5 text-[11px] font-mono text-[var(--accent)]">{litCount}</span>
            )}
          </button>
        ))}
      </div>

      {/* Body — tab content fills available space */}
      <div className="flex-1 overflow-y-auto">
        {tab === "diagnostic" && (
          <>
            {report?.warnings && report.warnings.length > 0 && (
              <WarningsBanner warnings={report.warnings} />
            )}
            {report && <ExportBar report={report} patientLabel={patientLabel} />}
            <DiagnosticTab report={report} patientLabel={patientLabel} />
          </>
        )}
        {tab === "debate"     && <DebateTab report={report} agents={agents} />}
        {tab === "literature" && <LiteratureTab literature={report?.literature} />}
      </div>

      {/* Pipeline — collapsible at the bottom, always visible */}
      <div className="border-t border-[var(--rule-strong)] max-h-[40vh] overflow-y-auto">
        <AgentList agents={agents} agentLabels={AGENT_LABELS} isRunning={isRunning} />
      </div>

      {/* Footer actions */}
      <div className="mt-auto p-4 border-t border-[var(--rule-strong)] bg-[var(--paper-2)] flex gap-2">
        <button className="flex-1 py-2.5 px-3 text-[12px] font-medium border border-[var(--rule-strong)] bg-transparent hover:bg-[var(--paper)] text-[var(--ink)]">
          Différer · cas suivant
        </button>
        <button
          disabled={!report}
          className="flex-1 py-2.5 px-3 text-[12px] font-medium bg-[var(--ink)] text-[var(--paper)] border border-[var(--ink)] hover:bg-[var(--accent)] hover:border-[var(--accent)] disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Valider et signer · CAP
        </button>
      </div>
    </aside>
  )
}

function ExportBar({ report, patientLabel }: { report: Report; patientLabel?: string }) {
  const [busy, setBusy] = useState<string | null>(null)
  const slug = (patientLabel ?? "rapport").replace(/[^a-zA-Z0-9_-]/g, "_") || "rapport"
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? ""

  const downloadBlob = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  const exportFile = async (kind: "pdf" | "docx") => {
    if (busy) return
    setBusy(kind)
    try {
      const res = await fetch(`${apiUrl}/api/report/${kind}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ report, patient_label: patientLabel ?? "", filename: slug }),
      })
      if (!res.ok) throw new Error(`export ${kind} failed: ${res.status}`)
      downloadBlob(await res.blob(), `${slug}.${kind}`)
    } catch (e) {
      console.error(e)
      alert(`Export ${kind.toUpperCase()} indisponible. Le backend est-il accessible ?`)
    } finally {
      setBusy(null)
    }
  }

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" })
    downloadBlob(blob, `${slug}.json`)
  }

  return (
    <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-b border-[var(--rule)] bg-[var(--paper-2)]">
      <div className="flex flex-col">
        <span className="smcaps !text-[var(--ink)] !text-[9.5px]">Rapport CAP</span>
        <span className={`font-mono text-[10px] ${(report.confidence ?? 1) < 0.70 ? "text-red-600 font-semibold" : "text-[var(--muted)]"}`}>v1.4 · {report.confidence ? `τ ${report.confidence.toFixed(2)}${report.confidence < 0.70 ? " · LOW" : ""}` : ""}</span>
      </div>
      <div className="flex">
        <ExpBtn label="PDF"  onClick={() => exportFile("pdf")}  busy={busy === "pdf"} />
        <ExpBtn label="DOCX" onClick={() => exportFile("docx")} busy={busy === "docx"} />
        <ExpBtn label="JSON" onClick={exportJson} />
        <ExpBtn label="DPI"  onClick={() => alert("Envoi DPI/HL7 — à connecter au SIH.")} />
      </div>
    </div>
  )
}

function ExpBtn({ label, onClick, busy }: { label: string; onClick: () => void; busy?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      className="flex items-center gap-1.5 px-2.5 py-1.5 font-mono text-[10.5px] font-medium text-[var(--ink-soft)] border border-[var(--rule-strong)] border-r-0 last:border-r bg-[var(--paper)] hover:bg-[var(--ink)] hover:text-[var(--paper)] disabled:opacity-50 disabled:cursor-wait transition-colors"
    >
      <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 3v12" /><path d="M7 10l5 5 5-5" /><path d="M5 21h14" />
      </svg>
      {busy ? "…" : label}
    </button>
  )
}
