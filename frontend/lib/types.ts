export type SlideStatus = 'idle' | 'uploading' | 'ready'

export interface Slide {
  id: string
  name: string
  size: number
  status: SlideStatus
  thumbnailUrl?: string
}

export type AgentName =
  | 'tile-triage'
  | 'histopathologist'
  | 'cross-slide-aggregator'
  | 'literature-hunter'
  | 'differential-diagnostician'
  | 'quality-control'
  | 'report-writer'

export type AgentStatus = 'pending' | 'running' | 'done' | 'error'

export interface AgentState {
  name: AgentName
  label: string
  status: AgentStatus
  messages: string[]
  confidence?: number
}

export interface WSEvent {
  type: 'agent_start' | 'agent_message' | 'agent_done' | 'analysis_complete'
  agent: AgentName
  message?: string
  confidence?: number
  report_id?: string
}

export interface Report {
  id: string
  patientId: string
  diagnosis: string
  grade: string
  confidence: number
  biomarkers: string[]
  margins: string
  similarCases: number
  slides: string[]
}
