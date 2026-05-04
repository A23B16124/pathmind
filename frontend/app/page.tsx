'use client'
import { useState } from 'react'
import { AgentPanel } from '@/components/agents/AgentPanel'
import { SlideUpload } from '@/components/upload/SlideUpload'
import { WSIViewer } from '@/components/viewer/WSIViewer'
import { AgentState, Slide, WSEvent } from '@/lib/types'
import { createMockStream } from '@/lib/ws'

const INITIAL_AGENTS: AgentState[] = [
  { name: 'tile-triage', label: 'Tile Triage', status: 'pending', messages: [] },
  { name: 'histopathologist', label: 'Histopathologist', status: 'pending', messages: [] },
  { name: 'cross-slide-aggregator', label: 'Cross-Slide Aggregator', status: 'pending', messages: [] },
  { name: 'literature-hunter', label: 'Literature Hunter', status: 'pending', messages: [] },
  { name: 'differential-diagnostician', label: 'Differential Diagnostician', status: 'pending', messages: [] },
  { name: 'quality-control', label: 'Quality Control', status: 'pending', messages: [] },
  { name: 'report-writer', label: 'Report Writer', status: 'pending', messages: [] },
]

export default function Home() {
  const [agents, setAgents] = useState<AgentState[]>(INITIAL_AGENTS)
  const [vramPct, setVramPct] = useState(0.12)
  const [slides, setSlides] = useState<Slide[]>([])

  const handleEvent = (event: WSEvent) => {
    setAgents((prev) =>
      prev.map((a) => {
        if (a.name !== event.agent) return a
        switch (event.type) {
          case 'agent_start':
            return { ...a, status: 'running' }
          case 'agent_message':
            return {
              ...a,
              messages: event.message ? [...a.messages, event.message] : a.messages,
              confidence: event.confidence ?? a.confidence,
            }
          case 'agent_done':
            return { ...a, status: 'done', confidence: event.confidence ?? a.confidence }
          default:
            return a
        }
      }),
    )
    if (event.type === 'agent_start') setVramPct((v) => Math.min(0.95, v + 0.1))
    if (event.type === 'agent_done') setVramPct((v) => Math.max(0.12, v - 0.05))
  }

  const handleSlides = (newSlides: Slide[]) => {
    setSlides(newSlides)
    setAgents(INITIAL_AGENTS)
    setVramPct(0.12)
    createMockStream(handleEvent)
  }

  return (
    <div className="flex h-screen bg-zinc-950 text-zinc-100">
      <aside className="w-72 border-r border-zinc-800 bg-zinc-950">
        <SlideUpload onSlides={handleSlides} />
      </aside>
      <main className="flex-1 bg-zinc-950">
        <WSIViewer slideId={slides[0]?.name ?? 'Aucune lame'} className="h-full" />
      </main>
      <aside className="w-96 border-l border-zinc-800 bg-zinc-950">
        <AgentPanel agents={agents} vramPct={vramPct} />
      </aside>
    </div>
  )
}
