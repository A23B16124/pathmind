import { WSEvent } from './types'

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8766'

export function createWSClient(onEvent: (event: WSEvent) => void): () => void {
  const ws = new WebSocket(WS_URL)

  ws.onmessage = (msg) => {
    try {
      const event: WSEvent = JSON.parse(msg.data)
      onEvent(event)
    } catch {
      // ignore malformed
    }
  }

  return () => ws.close()
}

// Mock for dev — removes itself when real WS connects
export function createMockStream(onEvent: (event: WSEvent) => void): () => void {
  const agents = [
    'tile-triage',
    'histopathologist',
    'cross-slide-aggregator',
    'literature-hunter',
    'differential-diagnostician',
    'quality-control',
    'report-writer',
  ] as const

  let i = 0
  const interval = setInterval(() => {
    if (i >= agents.length) {
      onEvent({ type: 'analysis_complete', agent: 'report-writer', report_id: 'mock-001' })
      clearInterval(interval)
      return
    }
    onEvent({ type: 'agent_start', agent: agents[i] })
    setTimeout(() => {
      onEvent({
        type: 'agent_message',
        agent: agents[i],
        message: getMockMessage(agents[i]),
        confidence: 0.7 + Math.random() * 0.25,
      })
      setTimeout(() => {
        onEvent({ type: 'agent_done', agent: agents[i], confidence: 0.85 + Math.random() * 0.1 })
        i++
      }, 1500)
    }, 800)
  }, 3000)

  return () => clearInterval(interval)
}

function getMockMessage(agent: string): string {
  const messages: Record<string, string> = {
    'tile-triage': 'Detection de 847 regions dinteret sur 12 lames. Focus zones perinucleaires.',
    'histopathologist': 'Analyse lame 7/12 — architecture canalaire infiltrante, cellules pleomorphes grade III.',
    'cross-slide-aggregator': 'Coherence inter-lames confirmee. Envahissement marginal detecte lames 8-9.',
    'literature-hunter': '847 cas similaires TCGA breast cancer. 12 abstracts PubMed pertinents.',
    'differential-diagnostician': 'DDx 1: CDI grade III (91%) — DDx 2: CLI (7%) — DDx 3: DCIS (2%)',
    'quality-control': 'Challenge grade tumoral: agent histopath concede grade III apres reanalyse lame 11.',
    'report-writer': 'Rapport CAP genere. Carcinome canalaire infiltrant grade III. Confiance 91%.',
  }
  return messages[agent] || 'Traitement en cours...'
}
