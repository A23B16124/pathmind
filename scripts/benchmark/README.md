# PathMind benchmark — TCGA-COAD vs real pathologist reports

Pipeline de validation : 10 cas TCGA-COAD avec compte-rendu pathologiste reel,
comparaison field-by-field avec la sortie PathMind.

## Etapes

```bash
# 1. Query GDC API → manifest.json (10 cas avec PDF report + slides)
python3 01_query_gdc.py

# 2. Download slides + reports (~80 GB, 30-60 min)
python3 02_download.py

# 3. Parse PDFs + structured GDC fields → ground_truth.json
pip install pdfplumber requests
python3 03_extract_gt.py

# 4. Run pipeline on chaque cas, compare → results.json
python3 04_run_benchmark.py
```

## Sources

- **Structured GT** : GDC clinical fields (`primary_diagnosis`, `tumor_grade`, `ajcc_pathologic_stage`, `pT/pN/pM`, `morphology`, `site`)
- **PDF GT** : pathology report text → biomarkers IHC, margin status, LVI, PNI, lymph nodes

## Metriques

- `diagnosis_concordance` : token overlap (tolere "Adenocarcinoma" vs "Colon adenocarcinoma")
- `grade_concordance` : G1/G2/G3 normalise
- `stage_concordance` : Stage I/II/III/IV (drop a/b suffix)
- `avg_biomarker_recall` : % des biomarkers du compte-rendu retrouves dans la sortie PathMind
