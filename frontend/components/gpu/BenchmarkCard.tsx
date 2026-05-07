export function BenchmarkCard() {
  const rows = [
    { label: "Hardware",       mi300x: "1x AMD MI300X",      h100: "4x NVIDIA H100" },
    { label: "VRAM",           mi300x: "192 Go HBM3",        h100: "4x 80 Go = 320 Go" },
    { label: "Analyse / cas",  mi300x: "~90 s",              h100: "~4 min" },
    { label: "Coût GPU/cas",   mi300x: "$0.38",              h100: "~$1.20" },
    { label: "Modèles chargés",mi300x: "Qwen2.5-72B-VL + Meditron-70B", h100: "1 modèle / GPU" },
    { label: "Setup",          mi300x: "1 noeud",            h100: "4 noeuds" },
  ]

  return (
    <div className="border border-[var(--rule-strong)] bg-[var(--paper-2)] overflow-hidden">
      <div className="px-3.5 py-2 border-b border-[var(--rule)] bg-[var(--paper)]">
        <span className="font-mono text-[9.5px] uppercase tracking-[0.14em] text-[var(--muted)]">
          AMD MI300X vs NVIDIA H100
        </span>
      </div>
      <table className="w-full text-[11px]">
        <thead>
          <tr className="border-b border-[var(--rule)]">
            <th className="text-left px-3 py-1.5 font-mono text-[9px] text-[var(--muted)] uppercase tracking-widest w-[35%]"></th>
            <th className="text-left px-3 py-1.5 font-mono text-[9px] text-[var(--ok)] uppercase tracking-widest">MI300X</th>
            <th className="text-left px-3 py-1.5 font-mono text-[9px] text-[var(--muted)] uppercase tracking-widest">H100 x4</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.label} className={`border-b border-[var(--rule)] last:border-0 ${i % 2 === 0 ? "" : "bg-[var(--paper)]"}`}>
              <td className="px-3 py-1.5 text-[var(--muted)] font-mono text-[10px]">{r.label}</td>
              <td className="px-3 py-1.5 text-[var(--ink)] font-medium">{r.mi300x}</td>
              <td className="px-3 py-1.5 text-[var(--muted)]">{r.h100}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
