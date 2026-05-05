"use client"
import { LiteratureBundle, LiteraturePaper } from "@/lib/types"

interface Props {
  literature?: LiteratureBundle
}

export function LiteratureTab({ literature }: Props) {
  if (!literature) {
    return (
      <div className="p-6 font-serif text-[14px] text-[var(--muted)] italic leading-relaxed">
        Le Literature-Hunter cherchera dans 12k abstracts PubMed indexés et la cohorte TCGA
        dès que le diagnostic préliminaire sera prêt. Les références utilisées par le
        Chief et les suggestions complémentaires apparaîtront ci-dessous.
      </div>
    )
  }

  const { used_papers = [], suggested_papers = [], key_findings, similar_cases } = literature

  return (
    <div>
      {/* Synthèse */}
      {key_findings && (
        <div className="px-5 py-4 border-b border-[var(--rule)]">
          <div className="smcaps mb-2">Synthèse littérature</div>
          <p className="font-serif text-[14px] leading-[1.5] text-[var(--ink-soft)]">
            {key_findings}
          </p>
          <div className="mt-3 font-mono text-[11px] text-[var(--muted)]">
            {used_papers.length} cités · {suggested_papers.length} suggérés · {similar_cases} hits indexés
          </div>
        </div>
      )}

      {/* Cités */}
      <Section
        title="Références citées par le Chief"
        sub="Utilisées pour ancrer le diagnostic"
        accent
        papers={used_papers}
        emptyMsg="Aucune référence citée."
      />

      {/* Suggérées */}
      <Section
        title="Suggestions complémentaires"
        sub="Pertinentes mais non citées — à consulter"
        papers={suggested_papers}
        emptyMsg="Aucune suggestion supplémentaire."
      />
    </div>
  )
}

function Section({
  title, sub, accent, papers, emptyMsg,
}: {
  title: string; sub: string; accent?: boolean; papers: LiteraturePaper[]; emptyMsg: string;
}) {
  return (
    <div className="px-5 py-4 border-b border-[var(--rule)] last:border-b-0">
      <div className="flex items-baseline justify-between mb-3">
        <div>
          <div className={`smcaps ${accent ? "!text-[var(--accent)]" : ""}`}>{title}</div>
          <div className="text-[11px] text-[var(--muted)] mt-0.5">{sub}</div>
        </div>
        <span className="font-mono text-[11px] text-[var(--ink-soft)]">{papers.length}</span>
      </div>

      {papers.length === 0 ? (
        <div className="font-serif italic text-[12px] text-[var(--muted)] py-2">{emptyMsg}</div>
      ) : (
        <div className="space-y-3">
          {papers.map((p) => <PaperCard key={`${p.source}-${p.pmid}`} p={p} accent={accent} />)}
        </div>
      )}
    </div>
  )
}

function PaperCard({ p, accent }: { p: LiteraturePaper; accent?: boolean }) {
  const isTcga = p.source === "tcga_case"
  const refLabel = isTcga ? `TCGA · ${p.pmid}` : `PMID ${p.pmid}`
  const meta = [p.journal, p.year, p.authors].filter(Boolean).join(" · ")

  return (
    <a
      href={p.url || "#"}
      target="_blank"
      rel="noopener noreferrer"
      className={`block border ${accent ? "border-l-[3px] border-l-[var(--accent)] border-r-[var(--rule)] border-y-[var(--rule)]" : "border-[var(--rule)]"} bg-[var(--paper)] hover:bg-[var(--paper-2)] p-3 transition-colors`}
    >
      <div className="flex items-baseline justify-between gap-3 mb-1">
        <div className="font-mono text-[10px] uppercase tracking-[0.1em] text-[var(--muted)]">
          {refLabel}
        </div>
        <div className="font-mono text-[10px] text-[var(--ink-soft)] flex-shrink-0">
          τ {p.score.toFixed(2)}
        </div>
      </div>
      <div className="font-serif text-[14px] font-medium leading-[1.25] text-[var(--ink)] mb-1">
        {p.title}
      </div>
      {meta && <div className="text-[11px] text-[var(--muted)] mb-1.5">{meta}</div>}
      {p.relevance && (
        <div className="text-[12px] italic text-[var(--ink-soft)] mb-1.5 leading-[1.4]">
          {p.relevance}
        </div>
      )}
      {p.snippet && (
        <div className="text-[11px] text-[var(--ink-soft)] leading-[1.5] line-clamp-3 font-serif">
          {p.snippet}
        </div>
      )}
      <div className="mt-2 font-mono text-[10px] text-[var(--accent)] inline-flex items-center gap-1">
        Ouvrir la source
        <svg className="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M7 17L17 7M9 7h8v8" />
        </svg>
      </div>
    </a>
  )
}
