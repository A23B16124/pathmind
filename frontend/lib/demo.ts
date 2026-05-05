import { DemoCase, Slide } from './types'

/**
 * Demo cases.
 *
 * - DEMO_DUBOIS  : fictional pancreatic case using the bundled OpenSlide test images.
 *                  Useful to demo the pipeline without hitting the network.
 * - DEMO_TCGA_BRCA : real TCGA breast case (lobular carcinoma, stage IIA).
 * - DEMO_TCGA_PAAD : real TCGA pancreatic case (PDAC, stage III, G2).
 *
 * The TCGA slide files (~3 GB each) are fetched on the MI300X cloud machine via
 * `python3 scripts/fetch_tcga_cases.py --download` and dropped into
 * `data/slides/tcga/`. The frontend just references them by name.
 */

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

export const DEMO_TCGA_BRCA: DemoCase = {
  case_id: 'tcga-OL-A66K',
  patient_id: 'TCGA-OL-A66K',
  patient_label: 'Patiente TCGA-OL-A66K · sein',
  age: 0,
  clinical_context:
    'Macrobiopsie mammaire — recherche carcinome canalaire infiltrant. ' +
    'Diagnostic TCGA documenté : carcinome lobulaire, stade IIA. ' +
    'Statut HER2, ER/PR, Ki-67 à confirmer en IHC.',
  slide_paths: [
    'tcga/TCGA-OL-A66K-01Z-00-DX1.C1DC85F1-4FAE-4411-9886-11DCB5E70CC3.svs',
    'tcga/TCGA-OL-A66K-01Z-00-DX2.svs',
  ],
  slide_names: [
    'TCGA-OL-A66K-DX1.svs',
    'TCGA-OL-A66K-DX2.svs',
  ],
}

export const DEMO_TCGA_PAAD: DemoCase = {
  case_id: 'tcga-2L-AAQJ',
  patient_id: 'TCGA-2L-AAQJ',
  patient_label: 'Patient TCGA-2L-AAQJ · pancréas',
  age: 0,
  clinical_context:
    'Biopsie tête de pancréas — adénocarcinome canalaire infiltrant (TCGA documenté, ' +
    'stade III, grade G2). Évaluation marges, engainement périnerveux, invasion lymphovasculaire.',
  slide_paths: [
    'tcga/TCGA-2L-AAQJ-01Z-00-DX1.91D3718F-DF73-48BA-BCB8-A00A000043F7.svs',
    'tcga/TCGA-2L-AAQJ-01Z-00-DX2.svs',
    'tcga/TCGA-2L-AAQJ-01Z-00-DX3.svs',
  ],
  slide_names: [
    'TCGA-2L-AAQJ-DX1.svs',
    'TCGA-2L-AAQJ-DX2.svs',
    'TCGA-2L-AAQJ-DX3.svs',
  ],
}

export const DEMO_CASES: DemoCase[] = [DEMO_DUBOIS, DEMO_TCGA_BRCA, DEMO_TCGA_PAAD]

/** Approximate sizes for the slide list UI before the file is actually downloaded. */
const SIZE_HINTS_MB: Record<string, number> = {
  'Dubois-tete-pancreas-01.svs': 2,
  'Dubois-tete-pancreas-02.svs': 61,
  'Dubois-tete-pancreas-03.svs': 127,
  'TCGA-OL-A66K-DX1.svs': 3243,
  'TCGA-OL-A66K-DX2.svs': 3100,
  'TCGA-2L-AAQJ-DX1.svs': 3228,
  'TCGA-2L-AAQJ-DX2.svs': 2950,
  'TCGA-2L-AAQJ-DX3.svs': 2800,
}

export function demoSlides(demo: DemoCase): Slide[] {
  return demo.slide_names.map((name, i) => ({
    id: `${demo.case_id}-${i}`,
    name,
    size: (SIZE_HINTS_MB[name] ?? 50) * 1024 * 1024,
    status: 'ready',
    path: demo.slide_paths[i],
  }))
}
