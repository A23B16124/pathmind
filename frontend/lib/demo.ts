import { DemoCase, Slide } from './types'

export const DEMO_DUBOIS: DemoCase = {
  case_id: 'dubois-2026-05',
  patient_id: 'P-DUBOIS-67',
  patient_label: 'M. Dubois, 67 ans',
  age: 67,
  clinical_context:
    'Homme 67 ans, douleurs épigastriques persistantes, perte de poids 8 kg en 3 mois. Echographie: masse pancréatique 32 mm tête du pancréas. Biopsie 12 lames.',
  slide_paths: [
    'data/slides/CMU-1-Small-Region.svs',
    'data/slides/JP2K-33003-1.svs',
    'data/slides/CMU-1-JP2K-33005.svs',
  ],
  slide_names: [
    'Dubois-tete-pancreas-01.svs',
    'Dubois-tete-pancreas-02.svs',
    'Dubois-tete-pancreas-03.svs',
  ],
}

export function demoSlides(demo: DemoCase): Slide[] {
  return demo.slide_names.map((name, i) => ({
    id: `${demo.case_id}-${i}`,
    name,
    size: i === 0 ? 1_900_000 : i === 1 ? 61_000_000 : 127_000_000,
    status: 'ready',
    path: demo.slide_paths[i],
  }))
}
