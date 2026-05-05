export type SlideStatus = 'idle' | 'uploading' | 'ready'

export interface Slide {
  id: string
  name: string
  size: number
  status: SlideStatus
  thumbnailUrl?: string
  path?: string
}

export type AgentName =
  | 'tile-triage'
  | 'histopathologist-a'
  | 'histopathologist-b'
  | 'cross-slide-aggregator'
  | 'literature-hunter'
  | 'chief'

export type AgentStatus = 'pending' | 'running' | 'done' | 'error'

export interface AgentState {
  name: AgentName
  label: string
  status: AgentStatus
  messages: string[]
  confidence?: number
}

export type WSEventType =
  | 'agent_start'
  | 'agent_message'
  | 'agent_done'
  | 'analysis_complete'
  | 'pipeline_start'
  | 'agent_error'

export interface ROIOverlay {
  x: number   // normalized 0..1
  y: number
  w: number
  h: number
  label?: string
  tissue?: number
  color?: string
}

export interface WSEvent {
  type: WSEventType
  agent: AgentName | 'pipeline'
  message?: string
  confidence?: number
  report_id?: string
  report?: Report
  slide?: number
  rois?: ROIOverlay[]
  slide_dims?: [number, number]
}

export interface LiteraturePaper {
  title: string
  pmid: string
  source: 'pubmed' | 'tcga_case' | string
  url: string
  score: number
  snippet: string
  journal?: string
  year?: string
  authors?: string
  relevance?: string
}

export interface LiteratureBundle {
  key_findings: string
  similar_cases: number
  used_papers: LiteraturePaper[]
  suggested_papers: LiteraturePaper[]
}

export interface ReportWarning {
  code: string
  severity: 'info' | 'warn' | 'danger'
  message: string
  evidence?: string
}

export interface Report {
  id?: string
  patientId?: string
  diagnosis: string
  grade?: string
  confidence: number
  biomarkers?: string[]
  margins?: string
  similarCases?: number
  slides?: string[]
  rawText?: string
  debate_summary?: string
  cap_report?: Record<string, unknown>
  report_html?: string
  primary_diagnosis?: string
  icd_o_code?: string
  pt_stage?: string
  pn_stage?: string
  margin_status?: string
  recommendations?: string[]
  similar_cases?: number
  literature?: LiteratureBundle
  warnings?: ReportWarning[]
}

export interface DemoCase {
  case_id: string
  patient_id: string
  patient_label: string
  age: number
  clinical_context: string
  slide_paths: string[]
  slide_names: string[]
}
