'use client'
import { AgentState, AgentStatus } from '@/lib/types'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'

const STATUS_COLOR: Record<AgentStatus, string> = {
  pending: 'bg-zinc-700 text-zinc-400',
  running: 'bg-blue-900 text-blue-300',
  done: 'bg-emerald-900 text-emerald-300',
  error: 'bg-red-900 text-red-300',
}

interface Props {
  agents: AgentState[]
  vramPct: number
}

export function AgentPanel({ agents, vramPct }: Props) {
  return (
    <div className="flex flex-col gap-4 p-4 h-full overflow-y-auto">
      <div className="space-y-1">
        <div className="flex justify-between text-xs text-zinc-400">
          <span>VRAM MI300X</span>
          <span>{Math.round(vramPct * 192)} / 192 GB</span>
        </div>
        <Progress value={vramPct * 100} className="h-1.5 bg-zinc-800" />
      </div>
      <div className="space-y-3">
        {agents.map((agent) => (
          <div key={agent.name} className="rounded-lg border border-zinc-800 bg-zinc-900 p-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">{agent.label}</span>
              <Badge className={STATUS_COLOR[agent.status]}>{agent.status}</Badge>
            </div>
            {agent.messages.length > 0 && (
              <p className="text-xs text-zinc-400 leading-relaxed">{agent.messages[agent.messages.length - 1]}</p>
            )}
            {agent.confidence !== undefined && (
              <div className="text-xs text-emerald-400">Confiance {Math.round(agent.confidence * 100)}%</div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
