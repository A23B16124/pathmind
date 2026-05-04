"use client"

export function PrintButton() {
  return (
    <button
      type="button"
      onClick={() => window.print()}
      className="px-5 py-2.5 rounded-md bg-[var(--accent)] hover:bg-[var(--accent)]/90 text-[#0d0a04] text-sm font-bold transition-colors shadow-lg shadow-[var(--accent)]/20 print:hidden"
    >
      Exporter PDF
    </button>
  )
}
