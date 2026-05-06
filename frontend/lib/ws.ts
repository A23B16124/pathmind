import { WSEvent, AgentName, Report } from './types'

const WS_URL = process.env.NEXT_PUBLIC_WS_URL
const API_URL = process.env.NEXT_PUBLIC_API_URL

const AGENT_NAMES: Record<string, AgentName> = {
  tile_triage: 'tile-triage',
  histopathologist: 'histopathologist-a',          // legacy fallback
  histopathologist_a: 'histopathologist-a',
  histopathologist_b: 'histopathologist-b',
  cross_slide_aggregator: 'cross-slide-aggregator',
  literature_hunter: 'literature-hunter',
  differential_diagnostician: 'chief',             // legacy fallback
  quality_control: 'chief',                         // legacy fallback
  report_writer: 'chief',                           // legacy fallback
  chief: 'chief',
}

function normalizeAgent(raw: string): AgentName | 'pipeline' {
  if (raw === 'pipeline') return 'pipeline'
  return AGENT_NAMES[raw] ?? (raw as AgentName)
}

import type { ROIOverlay } from './types'

interface BackendEvent {
  agent: string
  status: 'started' | 'running' | 'done' | 'complete' | 'error'
  content?: string
  confidence?: number
  slide?: number
  slide_idx?: number
  type?: string
  rois?: ROIOverlay[]
  slide_dims?: [number, number]
}

function backendToFrontend(ev: BackendEvent): WSEvent | null {
  const agent = normalizeAgent(ev.agent)

  if (agent === 'pipeline' && ev.status === 'complete') {
    let report: Report | undefined
    // Backend now sends a structured `report` field (preferred). Fall back to JSON-parsing content (legacy).
    const evWithReport = ev as BackendEvent & { report?: Report }
    if (evWithReport.report) {
      report = evWithReport.report
    } else {
      try {
        report = ev.content ? JSON.parse(ev.content) : undefined
      } catch {
        report = {
          diagnosis: ev.content ?? 'Diagnostic indisponible',
          confidence: ev.confidence ?? 0,
          rawText: ev.content,
        }
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
    return {
      type: 'agent_done',
      agent,
      confidence: ev.confidence,
      message: ev.content,
      slide: ev.slide,
      rois: ev.rois,
      slide_dims: ev.slide_dims,
    }
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

export async function fetchCachedReport(caseId: string): Promise<Report | null> {
  if (!API_URL) return null
  try {
    const res = await fetch(`${API_URL}/api/case/${encodeURIComponent(caseId)}/report`)
    if (!res.ok) return null
    const payload = await res.json()
    // Server returns {case_id, saved_at, report: {...}} — unwrap it.
    const report = (payload && payload.report) ? payload.report : payload
    return report as Report
  } catch {
    return null
  }
}

/**
 * Replay a cached report as a synthetic WS stream — agents flash through in
 * ~3 seconds so the user still sees the multi-agent debate UI without waiting
 * 5–10 minutes for the live pipeline. Real Tile-Triage ROIs (per slide) are
 * emitted from the cached `triage_results` so the WSIViewer overlays match
 * the agent output, not the mock fallbacks.
 */
export function replayFromCache(report: Report, onEvent: (event: WSEvent) => void): () => void {
  const agents: AgentName[] = [
    'tile-triage',
    'histopathologist-a',
    'histopathologist-b',
    'cross-slide-aggregator',
    'literature-hunter',
    'chief',
  ]
  const timers: ReturnType<typeof setTimeout>[] = []
  const STEP = 380

  // Pull real per-slide Tile-Triage ROIs out of the cache.
  type TriageEntry = { slide_index: number; regions_of_interest?: Array<Record<string, number | string>> }
  const reportRecord = report as unknown as Record<string, unknown>
  const triage = (reportRecord.triage_results as TriageEntry[] | undefined) ?? []
  const realRoisBySlide = new Map<number, ROIOverlay[]>()
  for (const t of triage) {
    const rois: ROIOverlay[] = (t.regions_of_interest ?? [])
      .map((r) => ({
        x: Number(r.x),
        y: Number(r.y),
        w: Number(r.w),
        h: Number(r.h),
        tissue: r.tissue_fraction !== undefined ? Number(r.tissue_fraction) : undefined,
        label: typeof r.roi_id === 'string' ? r.roi_id : undefined,
      }))
      .filter((r) => Number.isFinite(r.x) && Number.isFinite(r.y) && r.w > 0 && r.h > 0)
    if (rois.length > 0) realRoisBySlide.set(t.slide_index, rois)
  }

  agents.forEach((a, i) => {
    timers.push(setTimeout(() => onEvent({ type: 'agent_start', agent: a }), i * STEP))
    if (a === 'tile-triage' && realRoisBySlide.size > 0) {
      // Emit one agent_done per slide so overlaysBySlide gets populated correctly.
      const slideIndices = Array.from(realRoisBySlide.keys()).sort((x, y) => x - y)
      slideIndices.forEach((slideIdx, k) => {
        timers.push(setTimeout(
          () => onEvent({
            type: 'agent_done',
            agent: a,
            confidence: 0.85,
            slide: slideIdx,
            rois: realRoisBySlide.get(slideIdx),
          }),
          i * STEP + STEP - 80 - (slideIndices.length - 1 - k) * 60,
        ))
      })
    } else {
      timers.push(setTimeout(
        () => onEvent({ type: 'agent_done', agent: a, confidence: 0.85 + (i % 3) * 0.04 }),
        i * STEP + STEP - 80,
      ))
    }
  })
  timers.push(setTimeout(() => {
    onEvent({
      type: 'analysis_complete',
      agent: 'pipeline',
      confidence: report.confidence,
      report,
    })
  }, agents.length * STEP + 200))

  return () => timers.forEach(clearTimeout)
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
    'histopathologist-a',
    'histopathologist-b',
    'cross-slide-aggregator',
    'literature-hunter',
    'chief',
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
    'histopathologist-a': 'Histo-A (Qwen72B): infiltrating ductal architecture, grade III.',
    'histopathologist-b': 'Histo-B (Meditron70B): acinar variant pattern, grade II.',
    'cross-slide-aggregator': 'Inter-slide coherence — disagreement on grade II vs III, margin status.',
    'literature-hunter': '847 similar TCGA breast cases. 12 relevant PubMed abstracts.',
    'chief': 'Debate: 2 disagreements identified. Arbitrating grade and margin.',
  }
  return m[agent] ?? 'Processing...'
}
