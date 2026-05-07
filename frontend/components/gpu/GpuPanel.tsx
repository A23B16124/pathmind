"use client"
import { useState, useEffect } from "react"

interface GpuStats {
  vram_used_mb: number
  vram_total_mb: number
  gpu_util_pct: number
  source: string
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? ""

export function GpuPanel() {
  const [stats, setStats] = useState<GpuStats | null>(null)

  useEffect(() => {
    let cancelled = false
    const fetchStats = async () => {
      try {
        const res = await fetch(`${API_URL}/api/gpu-stats`, { cache: "no-store" })
        if (!res.ok) return
        const data: GpuStats = await res.json()
        if (!cancelled) setStats(data)
      } catch {}
    }
    fetchStats()
    const id = setInterval(fetchStats, 2000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  const usedGb = stats ? (stats.vram_used_mb / 1024) : 0
  const totalGb = stats ? (stats.vram_total_mb / 1024) : 192
  const pct = stats && stats.vram_total_mb > 0
    ? Math.round((stats.vram_used_mb / stats.vram_total_mb) * 100)
    : 0
  const utilPct = stats?.gpu_util_pct ?? 0
  const unavailable = !stats

  const barColor = pct > 80 ? "#6b1d1d" : pct > 50 ? "#b97a1c" : "#2f5d3a"

  return (
    <div className="font-mono text-[10.5px] border border-[var(--rule-strong)] bg-[var(--paper-2)] flex items-stretch h-8">
      {/* Label column */}
      <div className="flex flex-col justify-center px-2.5 border-r border-[var(--rule)] bg-[var(--paper)]">
        <span className="text-[8.5px] uppercase tracking-[0.14em] text-[var(--muted)] leading-none">MI300X</span>
        <span className="text-[8.5px] text-[var(--muted)] leading-none mt-0.5">192 Go HBM3</span>
      </div>
      {/* VRAM bar + value */}
      <div className="flex flex-col justify-center px-2.5 min-w-[120px]">
        <div className="flex items-center justify-between gap-2 leading-none">
          <span className="text-[8.5px] uppercase tracking-[0.14em] text-[var(--muted)]">VRAM</span>
          <span className="text-[10px] text-[var(--ink)] font-medium">
            {unavailable ? "—" : `${usedGb.toFixed(1)} / ${totalGb.toFixed(0)} Go`}
          </span>
        </div>
        <div className="h-1 bg-[var(--surface-2)] rounded-full overflow-hidden mt-1">
          <div
            className="h-full rounded-full transition-all duration-700"
            style={{ width: `${Math.max(2, Math.min(pct, 100))}%`, background: barColor }}
          />
        </div>
      </div>
      {/* GPU util */}
      <div className="flex flex-col justify-center px-2.5 border-l border-[var(--rule)] min-w-[58px]">
        <span className="text-[8.5px] uppercase tracking-[0.14em] text-[var(--muted)] leading-none">GPU</span>
        <span className="text-[10px] text-[var(--ink)] font-medium leading-none mt-0.5">{utilPct}%</span>
      </div>
    </div>
  )
}
