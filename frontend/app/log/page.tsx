"use client"
import { useEffect, useState, useRef } from "react"

interface LogEvent {
  ts: number
  case_id: string
  agent: string
  status: string
  content: string
  confidence?: number
}

const STATUS_COLOR: Record<string, string> = {
  started:  "text-blue-400",
  running:  "text-amber-400",
  done:     "text-emerald-400",
  complete: "text-emerald-400",
  error:    "text-red-400",
}

const AGENT_COLOR: Record<string, string> = {
  "tile-triage":                "text-cyan-300",
  "foundation-uni2":            "text-purple-300",
  "foundation-virchow2":        "text-purple-300",
  "histopathologist-a":         "text-pink-300",
  "histopathologist-b":         "text-pink-300",
  "cross-slide-aggregator":     "text-orange-300",
  "literature-hunter":          "text-yellow-300",
  "differential-diagnostician": "text-emerald-300",
  "quality-control":            "text-red-300",
  "report-writer":              "text-fuchsia-300",
}

export default function LogPage() {
  const [logs, setLogs] = useState<LogEvent[]>([])
  const [paused, setPaused] = useState(false)
  const [filter, setFilter] = useState<string>("")
  const [agentFilter, setAgentFilter] = useState<string>("")
  const [autoscroll, setAutoscroll] = useState(true)
  const containerRef = useRef<HTMLDivElement>(null)
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? ""

  useEffect(() => {
    if (paused) return
    let mounted = true
    let lastTs = 0
    let inflight = false
    const seen = new Set<string>()

    const keyOf = (l: LogEvent) => `${l.ts}|${l.agent}|${l.status}|${l.content.slice(0, 64)}`

    const tick = async () => {
      if (inflight) return
      inflight = true
      try {
        const r = await fetch(`${apiUrl}/api/logs?limit=500&since=${lastTs}`)
        const data = await r.json()
        if (!mounted) return
        if (data.logs && data.logs.length > 0) {
          const incoming = data.logs.reverse() as LogEvent[]
          const fresh = incoming.filter(l => {
            const k = keyOf(l)
            if (seen.has(k)) return false
            seen.add(k)
            return true
          })
          if (fresh.length > 0) {
            setLogs(prev => [...prev, ...fresh].slice(-1000))
            lastTs = Math.max(lastTs, ...fresh.map(l => l.ts))
          }
        }
      } catch {}
      finally { inflight = false }
    }

    tick()
    const id = setInterval(tick, 1000)
    return () => { mounted = false; clearInterval(id) }
  }, [paused, apiUrl])

  useEffect(() => {
    if (autoscroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [logs, autoscroll])

  const agents = Array.from(new Set(logs.map(l => l.agent))).sort()
  const filtered = logs.filter(l => {
    if (agentFilter && l.agent !== agentFilter) return false
    if (filter && !l.content.toLowerCase().includes(filter.toLowerCase()) && !l.agent.includes(filter)) return false
    return true
  })

  return (
    <div className="h-screen flex flex-col bg-zinc-950 text-zinc-100 font-mono text-[12.5px]">
      <header className="flex items-center gap-3 px-4 py-2.5 border-b border-zinc-800 bg-zinc-900">
        <div className="font-semibold text-[14px]">PathMind · Agent Logs</div>
        <span className="text-zinc-500">·</span>
        <span className="text-zinc-400">{filtered.length} events</span>
        <div className="flex-1" />
        <input
          type="text"
          placeholder="filter content..."
          value={filter}
          onChange={e => setFilter(e.target.value)}
          className="px-2 py-1 bg-zinc-800 border border-zinc-700 rounded text-[12px] w-48"
        />
        <select
          value={agentFilter}
          onChange={e => setAgentFilter(e.target.value)}
          className="px-2 py-1 bg-zinc-800 border border-zinc-700 rounded text-[12px]"
        >
          <option value="">all agents</option>
          {agents.map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <label className="flex items-center gap-1.5 text-[12px] text-zinc-400">
          <input type="checkbox" checked={autoscroll} onChange={e => setAutoscroll(e.target.checked)} />
          autoscroll
        </label>
        <button
          onClick={() => setPaused(p => !p)}
          className={`px-3 py-1 rounded text-[12px] ${paused ? "bg-emerald-700 hover:bg-emerald-600" : "bg-zinc-700 hover:bg-zinc-600"}`}
        >
          {paused ? "resume" : "pause"}
        </button>
        <button
          onClick={() => setLogs([])}
          className="px-3 py-1 rounded text-[12px] bg-zinc-700 hover:bg-zinc-600"
        >
          clear
        </button>
      </header>

      <div ref={containerRef} className="flex-1 overflow-y-auto p-3 space-y-0.5">
        {filtered.length === 0 && (
          <div className="text-zinc-500 italic">No logs yet. Run a case to see events stream in.</div>
        )}
        {filtered.map((l, i) => {
          const t = new Date(l.ts * 1000)
          const tstr = t.toISOString().slice(11, 23)
          return (
            <div key={i} className="flex gap-2 hover:bg-zinc-900 px-1">
              <span className="text-zinc-600 shrink-0">{tstr}</span>
              <span className={`shrink-0 w-44 truncate ${AGENT_COLOR[l.agent] || "text-zinc-300"}`}>{l.agent}</span>
              <span className={`shrink-0 w-16 ${STATUS_COLOR[l.status] || "text-zinc-400"}`}>{l.status}</span>
              <span className="text-zinc-200 break-words">{l.content}</span>
              {l.confidence !== undefined && l.confidence !== null && (
                <span className="text-zinc-500 shrink-0">τ {l.confidence.toFixed(2)}</span>
              )}
              <span className="text-zinc-700 shrink-0 ml-auto">{l.case_id.slice(0, 16)}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
