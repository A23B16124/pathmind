import { WSEvent, AgentName, Report } from './types'

const WS_URL = process.env.NEXT_PUBLIC_WS_URL
const API_URL = process.env.NEXT_PUBLIC_API_URL

const AGENT_NAMES: Record<string, AgentName> = {
  tile_triage: 'tile-triage',
  histopathologist: 'histopathologist',
  cross_slide_aggregator: 'cross-slide-aggregator',
  literature_hunter: 'literature-hunter',
  differential_diagnostician: 'differential-diagnostician',
  quality_control: 'quality-control',
  report_writer: 'report-writer',
}

function normalizeAgent(raw: string): AgentName | 'pipeline' {
  if (raw === 'pipeline') return 'pipeline'
  return AGENT_NAMES[raw] ?? (raw as AgentName)
}

interface BackendEvent {
  agent: string
  status: 'started' | 'running' | 'done' | 'complete' | 'error'
  content?: string
  confidence?: number
  slide_idx?: number
  type?: string
}

function backendToFrontend(ev: BackendEvent): WSEvent | null {
  const agent = normalizeAgent(ev.agent)

  if (agent === 'pipeline' && ev.status === 'complete') {
    let report: Report | undefined
    try {
      report = ev.content ? JSON.parse(ev.content) : undefined
    } catch {
      report = {
        diagnosis: ev.content ?? 'Diagnostic indisponible',
        confidence: ev.confidence ?? 0,
        rawText: ev.content,
      }
    }
    return { type: 'analysis_complete', agent, confidence: ev.confidence, report }
  }
  if (agent === 'pipeline' && ev.status === 'started') {
    return { type: 'pipeline_start', agent }
  }
  if (ev.status === 'running' || ev.status === 'started') {
    return { type: 'agent_start', agent, message: ev.content }
  }
  if (ev.status === 'done' || ev.status === 'complete') {
    return { type: 'agent_done', agent, confidence: ev.confidence, message: ev.content }
  }
  if (ev.status === 'error') {
    return { type: 'agent_error', agent, message: ev.content }
  }
  return { type: 'agent_message', agent, message: ev.content, confidence: ev.confidence }
}

export interface AnalyzeRequest {
  case_id: string
  patient_id: string
  slide_paths: string[]
  clinical_data?: Record<string, unknown>
}

export async function startAnalysis(req: AnalyzeRequest): Promise<void> {
  if (!API_URL) throw new Error('NEXT_PUBLIC_API_URL not set')
  const res = await fetch(`${API_URL}/api/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) throw new Error(`analyze failed: ${res.status}`)
}

export function connectStream(caseId: string, onEvent: (event: WSEvent) => void): () => void {
  if (!WS_URL) {
    console.warn('NEXT_PUBLIC_WS_URL not set, falling back to mock')
    return createMockStream(onEvent)
  }
  const base = WS_URL.replace(/\/[^/]*$/, '')
  const url = `${base}/${caseId}`
  let closed = false
  let ws: WebSocket | null = null

  const open = () => {
    ws = new WebSocket(url)
    ws.onmessage = (msg) => {
      try {
        const raw = JSON.parse(msg.data) as BackendEvent
        const frontEv = backendToFrontend(raw)
        if (frontEv) onEvent(frontEv)
      } catch {}
    }
    ws.onclose = () => {
      if (!closed) setTimeout(open, 1500)
    }
  }
  open()

  return () => {
    closed = true
    ws?.close()
  }
}

export function createMockStream(onEvent: (event: WSEvent) => void): () => void {
  const agents: AgentName[] = [
    'tile-triage',
    'histopathologist',
    'cross-slide-aggregator',
    'literature-hunter',
    'differential-diagnostician',
    'quality-control',
    'report-writer',
  ]

  let i = 0
  const timers: ReturnType<typeof setTimeout>[] = []
  const tick = () => {
    if (i >= agents.length) {
      onEvent({
        type: 'analysis_complete',
        agent: 'pipeline',
        confidence: 0.91,
        report: {
          diagnosis: 'Infiltrating ductal carcinoma grade III, clear margins',
          confidence: 0.91,
          grade: 'III',
          biomarkers: ['ER+', 'PR+', 'HER2-', 'Ki-67 35%'],
          margins: 'R0',
          similarCases: 847,
        },
      })
      return
    }
    const a = agents[i]
    onEvent({ type: 'agent_start', agent: a })
    timers.push(setTimeout(() => {
      onEvent({ type: 'agent_message', agent: a, message: getMockMessage(a) })
      timers.push(setTimeout(() => {
        onEvent({ type: 'agent_done', agent: a, confidence: 0.85 + Math.random() * 0.1 })
        i++
        timers.push(setTimeout(tick, 600))
      }, 1400))
    }, 700))
  }
  tick()

  return () => timers.forEach(clearTimeout)
}

function getMockMessage(agent: AgentName): string {
  const m: Record<AgentName, string> = {
    'tile-triage': '847 ROIs detected across 12 slides. Focused on perinuclear zones.',
    histopathologist: 'Infiltrating ductal architecture, grade III pleomorphic cells.',
    'cross-slide-aggregator': 'Inter-slide coherence confirmed. Marginal invasion slides 8-9.',
    'literature-hunter': '847 similar TCGA breast cases. 12 relevant PubMed abstracts.',
    'differential-diagnostician': 'DDx 1: IDC grade III (91%) — DDx 2: ILC (7%) — DDx 3: DCIS (2%)',
    'quality-control': 'Histopath agent reviewed: grade III confirmed. QC score 0.93.',
    'report-writer': 'CAP report generated. IDC grade III. Confidence 91%.',
  }
  return m[agent] ?? 'Traitement en cours...'
}
