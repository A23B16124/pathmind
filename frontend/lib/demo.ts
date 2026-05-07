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
  case_id: 'tcga-TCGA-OL-A66K',
  patient_id: 'TCGA-OL-A66K',
  patient_label: 'Patiente A66K · sein',
  age: 0,
  clinical_context:
    'Femme, macrobiopsie mammaire pour masse palpable quadrant supéro-externe. ' +
    'Mammographie : opacité spiculée 22 mm, ACR 5. Pas d\'adénopathie axillaire palpable. ' +
    'Demande : caractérisation histologique, grade, statut ER/PR/HER2/Ki-67 à prévoir en IHC.',
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
  case_id: 'tcga-TCGA-2L-AAQJ',
  patient_id: 'TCGA-2L-AAQJ',
  patient_label: 'Patient AAQJ · pancréas',
  age: 0,
  clinical_context:
    'Femme, ictère obstructif progressif et perte de poids 6 kg sur 2 mois. ' +
    'TDM : masse hypodense 28 mm tête du pancréas, dilatation Wirsung et VBP. CA 19-9 élevé. ' +
    'Biopsie écho-endoscopique. Demande : nature de la lésion, grade, marges, engainement périnerveux, invasion lymphovasculaire.',
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

export const DEMO_TCGA_LUAD: DemoCase = {
  case_id: 'tcga-TCGA-44-2657',
  patient_id: 'TCGA-44-2657',
  patient_label: 'Patient 2657 · poumon',
  age: 0,
  clinical_context:
    'Homme fumeur 30 PA, nodule lobe supérieur droit 28 mm découvert sur scanner thoracique. ' +
    'TEP-FDG : hyperfixation focale, pas de localisation à distance. Lobectomie supérieure droite + curage. ' +
    'Demande : nature, grade nucléaire, sous-type prédominant (lépidique/acineux/papillaire/micropapillaire/solide), invasion pleurale, statut ganglionnaire.',
  slide_paths: [
    'tcga/TCGA-44-2657-01Z-00-DX1.A12B3C4D-5E6F-7A8B-9C0D-1E2F3A4B5C6D.svs',
    'tcga/TCGA-44-2657-01A-01-TS1.B23C4D5E-6F7A-8B9C-0D1E-2F3A4B5C6D7E.svs',
  ],
  slide_names: [
    'TCGA-44-2657-DX1.svs',
    'TCGA-44-2657-TS1.svs',
  ],
}


export const DEMO_TCGA_COAD: DemoCase = {
  case_id: 'tcga-TCGA-A6-5659',
  patient_id: 'TCGA-A6-5659',
  patient_label: 'Patient A6-5659 — côlon',
  age: 82,
  sex: 'M',
  site: 'Côlon ascendant / cæcum',
  sample_type: 'Hémicolectomie droite — 6 lames (1 DX, 5 TS/BS multi-blocs)',
  prior_history: 'Pas d\'antécédent néoplasique. Pas de traitement antitumoral antérieur.',
  clinical_context:
    'Homme 82 ans. Anémie ferriprive d\'apparition récente (Hb 9,8 g/dL), asthénie, perte de poids 5 kg en 2 mois, transit alterné. ' +
    'Examen : abdomen souple, pas de masse palpable, TR sans particularité. ' +
    'Biologie : Hb 9,8 — ferritine 8 µg/L — CRP 28 — ACE 12 ng/mL. ' +
    'Coloscopie totale : lésion bourgeonnante sténosante du côlon ascendant à 110 cm de la marge anale, biopsies multiples puis hémicolectomie droite avec curage. ' +
    'TDM TAP : épaississement pariétal cæcal, pas d\'adénomégalie suspecte, foie sans lésion focale, pas de carcinose. ' +
    'Pas d\'antécédent personnel ni familial connu de pathologie colique. ' +
    'Demande : nature de la lésion, grade, profondeur d\'invasion (pT), marges chirurgicales, engainement périnerveux (PNI), invasion lymphovasculaire (LVI), nombre de ganglions envahis sur le curage, statut MSI à prévoir si carcinome confirmé.',
  slide_paths: [
    'tcga/TCGA-A6-5659-01Z-00-DX1.c671806f-013e-4d99-9841-cda5bd43eff1.svs',
    'tcga/TCGA-A6-5659-01A-01-TS1.dbb4f3d2-3b68-4642-a4ef-c168571f807e.svs',
    'tcga/TCGA-A6-5659-01A-01-BS1.68fc1dd8-b1fd-451b-95ba-ec402bfb84b6.svs',
    'tcga/TCGA-A6-5659-01B-03-BS3.D77C3B01-5D98-43AE-AA4C-FB1C3C5EA0A8.svs',
    'tcga/TCGA-A6-5659-01B-04-BS4.3557F6B1-2DB8-48FA-87A0-86B293BA9FFC.svs',
    'tcga/TCGA-A6-5659-11A-01-TS1.d1a844c4-de66-4210-9201-8b74b14fea32.svs',
  ],
  slide_names: [
    'TCGA-A6-5659-DX1.svs',
    'TCGA-A6-5659-TS1.svs',
    'TCGA-A6-5659-BS1.svs',
    'TCGA-A6-5659-BS3.svs',
    'TCGA-A6-5659-BS4.svs',
    'TCGA-A6-5659-N-TS1.svs',
  ],
}

export const DEMO_CASES: DemoCase[] = [DEMO_DUBOIS, DEMO_TCGA_BRCA, DEMO_TCGA_PAAD, DEMO_TCGA_LUAD, DEMO_TCGA_COAD]

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
  'TCGA-44-2657-DX1.svs': 2848,
  'TCGA-44-2657-TS1.svs': 412,
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
