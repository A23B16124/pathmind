import Link from "next/link"
import { PrintButton } from "./PrintButton"

const PRINT_STYLES = `
@media print {
  @page { margin: 16mm; }
  html, body {
    background: #ffffff !important;
    color: #000000 !important;
    color-adjust: exact;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
  .print\\:hidden, header.sticky, footer.fixed { display: none !important; }
  main { padding-bottom: 0 !important; max-width: none !important; }
  section, .rounded-xl, .rounded-md, .rounded-full {
    background: #ffffff !important;
    box-shadow: none !important;
    border-color: #d4d4d4 !important;
    color: #000000 !important;
  }
  h1, h2, h3, p, span, li, div { color: #000000 !important; }
  /* Force chips/bars to keep their accent colors */
  [class*="bg-[var(--accent)]"],
  [class*="text-[var(--accent)]"],
  [class*="border-[var(--accent)]"] { color: #b8860b !important; border-color: #b8860b !important; }
  [class*="bg-[var(--error)]"],
  [class*="text-[var(--error)]"],
  [class*="border-[var(--error)]"] { color: #b91c1c !important; border-color: #b91c1c !important; }
  [class*="bg-[var(--running)]"],
  [class*="text-[var(--running)]"],
  [class*="border-[var(--running)]"] { color: #1d4ed8 !important; border-color: #1d4ed8 !important; }
  [class*="bg-[var(--done)]"],
  [class*="text-[var(--done)]"],
  [class*="border-[var(--done)]"] { color: #15803d !important; border-color: #15803d !important; }
  /* Confidence bar fill */
  .h-2 > .bg-\\[var\\(--done\\)\\] { background: #15803d !important; }
  .w-2.h-2 { background: #b91c1c !important; }
}
`

const DIAGNOSIS = "Adénocarcinome pancréatique ductal infiltrant"
const GRADE = "Grade II/III (OMS 2022)"
const CONFIDENCE = 87
const MARGINS = "Marges envahies R1 — marge postérieure < 1 mm"

const BIOMARKERS: { label: string; tone: "amber" | "rose" | "blue" | "green" }[] = [
  { label: "KI-67 42%", tone: "amber" },
  { label: "TP53 mut", tone: "rose" },
  { label: "SMAD4 perte", tone: "rose" },
  { label: "CA19-9 élevé", tone: "blue" },
]

const CLINICAL_CONTEXT =
  "Patient : M. Dubois, 68 ans. Adressé pour exploration d'un ictère obstructif évoluant depuis 3 semaines, accompagné d'une perte pondérale de 7 kg en 2 mois. TDM thoraco-abdomino-pelvienne : masse de la tête du pancréas de 32 mm avec dilatation des voies biliaires et du Wirsung. Antécédents : tabagisme sevré (30 PA), diabète de type 2 récent (< 1 an). Marqueurs : CA 19-9 à 480 U/mL. Duodéno-pancréatectomie céphalique réalisée le 18/04/2026."

const SIMILAR_CASES = {
  count: 847,
  cohort: "TCGA-PAAD + ICGC-PACA-AU",
  medianSurvival: "18 mois",
  recurrenceRate: "62 % à 24 mois",
}

const RECOMMENDATIONS = [
  {
    title: "Chimiothérapie adjuvante",
    detail:
      "FOLFIRINOX modifié (mFOLFIRINOX) en 1ère intention si OMS 0-1, à débuter dans les 8 semaines post-opératoires (PRODIGE 24 / NEJM 2018).",
  },
  {
    title: "Discussion RCP",
    detail:
      "Présentation en Réunion de Concertation Pluridisciplinaire hépato-bilio-pancréatique pour validation du protocole et évaluation d'une radiothérapie de complément sur la marge R1.",
  },
  {
    title: "Suivi",
    detail:
      "TDM TAP + CA 19-9 tous les 3 mois pendant 2 ans, puis tous les 6 mois jusqu'à 5 ans.",
  },
]

const TONE_CLASSES: Record<string, string> = {
  amber: "border-[var(--accent)]/40 text-[var(--accent)] bg-[var(--accent)]/10",
  rose: "border-[var(--error)]/40 text-[var(--error)] bg-[var(--error)]/10",
  blue: "border-[var(--running)]/40 text-[var(--running)] bg-[var(--running)]/10",
  green: "border-[var(--done)]/40 text-[var(--done)] bg-[var(--done)]/10",
}

function formatDate(d: Date): string {
  return d.toLocaleDateString("fr-FR", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  })
}

export default async function ReportPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  const today = formatDate(new Date())

  return (
    <div className="min-h-screen bg-[var(--bg)] text-[var(--text)] flex flex-col overflow-y-auto">
      <header className="sticky top-0 z-20 border-b border-[var(--border)] bg-[var(--bg)]/95 backdrop-blur-md">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold tracking-tight">
              PathMind
              <span className="text-[var(--muted)] font-normal"> — Rapport CAP</span>
            </h1>
            <p className="text-xs font-mono text-[var(--muted)] mt-1">
              Généré le {today} <span className="mx-2 text-[var(--muted-2)]">|</span> Case ID{" "}
              <span className="text-[var(--accent)]">{id}</span>
            </p>
          </div>
          <Link
            href="/"
            className="px-4 py-2 rounded-md border border-[var(--border-2)] text-sm text-[var(--text)] hover:bg-[var(--surface)] transition-colors"
          >
            Retour
          </Link>
        </div>
      </header>

      <main className="flex-1 max-w-6xl w-full mx-auto px-6 py-8 space-y-8 pb-32">
        <section className="rounded-xl border border-[var(--border-2)] bg-[var(--surface-2)] p-8 shadow-2xl">
          <div className="flex items-baseline gap-3 mb-4">
            <span className="text-[10px] font-mono uppercase tracking-widest text-[var(--accent)]">
              Diagnostic principal
            </span>
            <span className="text-[10px] font-mono text-[var(--muted)]">
              Anatomopathologie chirurgicale
            </span>
          </div>

          <h2 className="text-3xl font-bold text-[var(--accent)] leading-tight mb-6">
            {DIAGNOSIS}
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
              <p className="text-[10px] font-mono uppercase tracking-widest text-[var(--muted)] mb-2">
                Grade
              </p>
              <p className="text-sm font-mono text-[var(--text)]">{GRADE}</p>
            </div>

            <div className="md:col-span-2">
              <div className="flex items-center justify-between mb-2">
                <p className="text-[10px] font-mono uppercase tracking-widest text-[var(--muted)]">
                  Confiance du modèle
                </p>
                <span className="text-sm font-mono font-bold text-[var(--done)]">
                  {CONFIDENCE}%
                </span>
              </div>
              <div className="h-2 rounded-full bg-[var(--border)] overflow-hidden">
                <div
                  className="h-full bg-[var(--done)] transition-all"
                  style={{ width: `${CONFIDENCE}%` }}
                />
              </div>
            </div>
          </div>

          <div className="mt-6 pt-6 border-t border-[var(--border)]">
            <p className="text-[10px] font-mono uppercase tracking-widest text-[var(--muted)] mb-2">
              Statut des marges
            </p>
            <div className="flex items-center gap-2">
              <span className="inline-block w-2 h-2 rounded-full bg-[var(--error)]" />
              <p className="text-sm font-mono text-[var(--error)]">{MARGINS}</p>
            </div>
          </div>
        </section>

        <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="space-y-6">
            <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
              <h3 className="text-sm font-bold uppercase tracking-widest text-[var(--accent)] mb-4">
                Biomarqueurs
              </h3>
              <div className="flex flex-wrap gap-2">
                {BIOMARKERS.map((b) => (
                  <span
                    key={b.label}
                    className={`text-xs font-mono px-3 py-1.5 rounded-md border ${TONE_CLASSES[b.tone]}`}
                  >
                    {b.label}
                  </span>
                ))}
              </div>
              <p className="text-xs text-[var(--muted)] mt-4 leading-relaxed">
                Profil moléculaire compatible avec un PDAC de pronostic défavorable.
                La perte de SMAD4 oriente vers un phénotype métastatique précoce.
              </p>
            </div>

            <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
              <h3 className="text-sm font-bold uppercase tracking-widest text-[var(--accent)] mb-4">
                Contexte clinique
              </h3>
              <p className="text-sm leading-relaxed text-[var(--text)]">
                {CLINICAL_CONTEXT}
              </p>
            </div>
          </div>

          <div className="space-y-6">
            <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
              <h3 className="text-sm font-bold uppercase tracking-widest text-[var(--accent)] mb-4">
                Cas similaires — TCGA
              </h3>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-3xl font-bold text-[var(--text)]">
                    {SIMILAR_CASES.count}
                  </p>
                  <p className="text-[10px] font-mono uppercase tracking-widest text-[var(--muted)] mt-1">
                    cas appariés
                  </p>
                </div>
                <div>
                  <p className="text-3xl font-bold text-[var(--text)]">
                    {SIMILAR_CASES.medianSurvival}
                  </p>
                  <p className="text-[10px] font-mono uppercase tracking-widest text-[var(--muted)] mt-1">
                    médiane de survie
                  </p>
                </div>
              </div>
              <div className="mt-4 pt-4 border-t border-[var(--border)] space-y-1.5">
                <p className="text-xs font-mono text-[var(--muted)]">
                  Cohorte : <span className="text-[var(--text)]">{SIMILAR_CASES.cohort}</span>
                </p>
                <p className="text-xs font-mono text-[var(--muted)]">
                  Récidive :{" "}
                  <span className="text-[var(--text)]">{SIMILAR_CASES.recurrenceRate}</span>
                </p>
              </div>
            </div>

            <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
              <h3 className="text-sm font-bold uppercase tracking-widest text-[var(--accent)] mb-4">
                Recommandations
              </h3>
              <ol className="space-y-4">
                {RECOMMENDATIONS.map((r, i) => (
                  <li key={r.title} className="flex gap-3">
                    <span className="flex-shrink-0 w-6 h-6 rounded-full border border-[var(--accent)]/40 bg-[var(--accent)]/10 text-[var(--accent)] text-xs font-mono font-bold flex items-center justify-center">
                      {i + 1}
                    </span>
                    <div>
                      <p className="text-sm font-bold text-[var(--text)] mb-1">{r.title}</p>
                      <p className="text-xs text-[var(--muted)] leading-relaxed">{r.detail}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </section>
      </main>

      <footer className="fixed bottom-0 left-0 right-0 z-20 border-t border-[var(--border)] bg-[var(--bg)]/95 backdrop-blur-md">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <p className="text-xs font-mono text-[var(--muted)]">
            Document généré par PathMind. À valider par le pathologiste référent.
          </p>
          <div className="flex items-center gap-3">
            <Link
              href="/"
              className="px-4 py-2.5 rounded-md border border-[var(--border-2)] text-sm text-[var(--text)] hover:bg-[var(--surface)] transition-colors"
            >
              Fermer
            </Link>
            <button
              type="button"
              className="px-5 py-2.5 rounded-md bg-[var(--accent)] hover:bg-[var(--accent)]/90 text-[#0d0a04] text-sm font-bold transition-colors shadow-lg shadow-[var(--accent)]/20"
            >
              Exporter PDF
            </button>
          </div>
        </div>
      </footer>
    </div>
  )
}
