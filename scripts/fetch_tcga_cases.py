"""
Pick 2 demo TCGA cases (1 BRCA + 1 PAAD) and emit:
  - the slide UUIDs (.svs Diagnostic Slides) so we can wget/gdc-client them
  - a DemoCase dict matching frontend/lib/demo.ts shape (clinical metadata)

Usage:
    python3 scripts/fetch_tcga_cases.py            # write JSON output to data/demo/
    python3 scripts/fetch_tcga_cases.py --download # also wget the slides into data/slides/tcga/
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Any

GDC_FILES = "https://api.gdc.cancer.gov/files"
GDC_CASES = "https://api.gdc.cancer.gov/cases"
GDC_DATA  = "https://api.gdc.cancer.gov/data"

# Storage layout
ROOT       = Path(__file__).resolve().parents[1]
DEMO_DIR   = ROOT / "data" / "demo"
SLIDES_DIR = ROOT / "data" / "slides" / "tcga"


def gdc_post(url: str, payload: dict) -> dict:
    """POST JSON to GDC API and return decoded response."""
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def find_diagnostic_slide(project_id: str, primary_diagnosis_filter: str | None = None) -> dict | None:
    """Find a single Diagnostic Slide .svs for a project. Returns the file payload."""
    filters: dict[str, Any] = {
        "op": "and",
        "content": [
            {"op": "in", "content": {"field": "cases.project.project_id", "value": [project_id]}},
            {"op": "in", "content": {"field": "data_format",                "value": ["SVS"]}},
            {"op": "in", "content": {"field": "experimental_strategy",      "value": ["Diagnostic Slide"]}},
            {"op": "in", "content": {"field": "access",                     "value": ["open"]}},
        ],
    }
    if primary_diagnosis_filter:
        filters["content"].append({
            "op": "in",
            "content": {"field": "cases.diagnoses.primary_diagnosis", "value": [primary_diagnosis_filter]},
        })

    payload = {
        "filters": filters,
        "fields": (
            "file_id,file_name,file_size,md5sum,"
            "cases.case_id,cases.submitter_id,"
            "cases.demographic.gender,cases.demographic.year_of_birth,"
            "cases.diagnoses.primary_diagnosis,cases.diagnoses.tumor_grade,"
            "cases.diagnoses.ajcc_pathologic_stage,cases.diagnoses.ajcc_pathologic_t,"
            "cases.diagnoses.ajcc_pathologic_n,cases.diagnoses.ajcc_pathologic_m,"
            "cases.diagnoses.morphology,cases.diagnoses.site_of_resection_or_biopsy,"
            "cases.diagnoses.perineural_invasion_present,cases.diagnoses.lymphovascular_invasion_present"
        ),
        "format": "JSON",
        "size": 8,
        "sort": "file_size:desc",
    }
    resp = gdc_post(GDC_FILES, payload)
    hits = resp.get("data", {}).get("hits", [])
    # Prefer hits that have rich clinical metadata (gender, stage)
    for h in hits:
        case = (h.get("cases") or [{}])[0]
        diag = (case.get("diagnoses") or [{}])[0]
        if diag.get("ajcc_pathologic_stage") or diag.get("primary_diagnosis"):
            return h
    return hits[0] if hits else None


def to_demo_case(file_hit: dict, *, label_fr: str, context_fr: str) -> dict:
    """Project a GDC file payload onto the DemoCase shape used by the frontend."""
    case = (file_hit.get("cases") or [{}])[0]
    demo = case.get("demographic") or {}
    diag = (case.get("diagnoses") or [{}])[0]
    yob  = demo.get("year_of_birth")
    age  = (2026 - int(yob)) if yob else 0

    return {
        "case_id":           f"tcga-{case.get('submitter_id', case.get('case_id', 'unknown'))}",
        "patient_id":        case.get("submitter_id", "unknown"),
        "patient_label":     label_fr,
        "age":               age,
        "clinical_context":  context_fr,
        "slide_paths":       [f"tcga/{file_hit.get('file_name')}"],
        "slide_names":       [file_hit.get("file_name")],
        # Provenance / metadata — used by the report and downloader
        "tcga": {
            "file_id":            file_hit.get("file_id"),
            "case_id":            case.get("case_id"),
            "submitter_id":       case.get("submitter_id"),
            "primary_diagnosis":  diag.get("primary_diagnosis"),
            "tumor_grade":        diag.get("tumor_grade"),
            "stage":              diag.get("ajcc_pathologic_stage"),
            "pt":                 diag.get("ajcc_pathologic_t"),
            "pn":                 diag.get("ajcc_pathologic_n"),
            "pm":                 diag.get("ajcc_pathologic_m"),
            "morphology":         diag.get("morphology"),
            "site":               diag.get("site_of_resection_or_biopsy"),
            "pni":                diag.get("perineural_invasion_present"),
            "lvi":                diag.get("lymphovascular_invasion_present"),
            "gender":             demo.get("gender"),
            "year_of_birth":      yob,
            "file_size_bytes":    file_hit.get("file_size"),
            "download_url":       f"{GDC_DATA}/{file_hit.get('file_id')}",
            "md5":                file_hit.get("md5sum"),
        },
    }


def download_slide(file_id: str, dest_path: Path) -> None:
    """Stream a slide from GDC. Skip if file already present and matches expected size (cheap check)."""
    if dest_path.exists() and dest_path.stat().st_size > 1_000_000:
        print(f"  ↺ already present: {dest_path.name} ({dest_path.stat().st_size / 1024**2:.1f} MB)")
        return
    url = f"{GDC_DATA}/{file_id}"
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"  ↓ downloading {url} → {dest_path.name}")
    urllib.request.urlretrieve(url, dest_path)
    print(f"    done: {dest_path.stat().st_size / 1024**2:.1f} MB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true", help="also wget the slides")
    args = ap.parse_args()

    DEMO_DIR.mkdir(parents=True, exist_ok=True)

    targets = [
        {
            "project_id":   "TCGA-BRCA",
            "label_fr":     "Patiente BRCA · TCGA",
            "context_fr":   "Macrobiopsie mammaire — recherche carcinome canalaire infiltrant. "
                            "Statut HER2 et Ki-67 à confirmer en IHC.",
        },
        {
            "project_id":   "TCGA-PAAD",
            "label_fr":     "Patient PAAD · TCGA",
            "context_fr":   "Biopsie tête de pancréas — adénocarcinome suspecté. "
                            "Évaluation marges, engainement périnerveux, invasion lymphovasculaire.",
        },
    ]

    out_cases = []
    for t in targets:
        print(f"\n→ Querying GDC for {t['project_id']}…")
        hit = find_diagnostic_slide(t["project_id"])
        if not hit:
            print(f"  ✗ no diagnostic slide found for {t['project_id']}")
            continue
        case = to_demo_case(hit, label_fr=t["label_fr"], context_fr=t["context_fr"])
        out_cases.append(case)
        print(f"  ✓ {case['tcga']['submitter_id']} — {case['tcga']['primary_diagnosis']!r}, stage={case['tcga']['stage']!r}, grade={case['tcga']['tumor_grade']!r}")
        print(f"    slide: {case['slide_names'][0]}  ({(case['tcga']['file_size_bytes'] or 0) / 1024**2:.1f} MB)")

        if args.download:
            print(f"  Downloading slide…")
            dest = SLIDES_DIR / case["slide_names"][0]
            try:
                download_slide(case["tcga"]["file_id"], dest)
            except Exception as e:
                print(f"  ✗ download failed: {e}")

    out = DEMO_DIR / "tcga_demo_cases.json"
    out.write_text(json.dumps(out_cases, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n✓ wrote {out} ({len(out_cases)} cases)")
    print(f"\nNext steps:")
    print(f"  1. Review {out}")
    print(f"  2. Add the cases to frontend/lib/demo.ts (or import the JSON)")
    print(f"  3. On the MI300X cloud machine: python3 scripts/fetch_tcga_cases.py --download")


if __name__ == "__main__":
    sys.exit(main() or 0)
