"""
Query GDC API for TCGA-COAD cases that have BOTH a pathology report PDF
AND at least one diagnostic slide image (SVS). Build a manifest of N new
cases (excluding ones we already have on disk).

Output: data/benchmark/manifest.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

GDC_FILES = "https://api.gdc.cancer.gov/files"
GDC_CASES = "https://api.gdc.cancer.gov/cases"
PROJECT = "TCGA-COAD"
N_CASES = 10
SLIDE_DIR = Path("/root/pathmind/data/slides/tcga")
OUT = Path("/root/pathmind/data/benchmark/manifest.json")


def existing_case_submitters() -> set[str]:
    """Cases we already partially have — extract TCGA-XX-XXXX prefix from filenames."""
    if not SLIDE_DIR.exists():
        return set()
    out = set()
    for p in SLIDE_DIR.glob("TCGA-*.svs"):
        parts = p.name.split("-")
        if len(parts) >= 3:
            out.add("-".join(parts[:3]))  # TCGA-A6-5659
    return out


def fetch_path_report_cases() -> list[dict]:
    """Cases with a Pathology Report (PDF) attached."""
    filters = {
        "op": "and",
        "content": [
            {"op": "in", "content": {"field": "cases.project.project_id", "value": [PROJECT]}},
            {"op": "in", "content": {"field": "data_type", "value": ["Pathology Report"]}},
        ],
    }
    fields = ",".join([
        "file_id", "file_name", "data_format",
        "cases.case_id", "cases.submitter_id",
        "cases.diagnoses.primary_diagnosis",
        "cases.diagnoses.tumor_grade",
        "cases.diagnoses.ajcc_pathologic_stage",
        "cases.diagnoses.ajcc_pathologic_t",
        "cases.diagnoses.ajcc_pathologic_n",
        "cases.diagnoses.ajcc_pathologic_m",
        "cases.diagnoses.morphology",
        "cases.diagnoses.site_of_resection_or_biopsy",
    ])
    r = requests.get(GDC_FILES, params={
        "filters": json.dumps(filters),
        "format": "json",
        "fields": fields,
        "size": 200,
    }, timeout=60)
    r.raise_for_status()
    return r.json()["data"]["hits"]


def fetch_slides_for_case(case_id: str) -> list[dict]:
    """All SVS files for a given case_id."""
    filters = {
        "op": "and",
        "content": [
            {"op": "=", "content": {"field": "cases.case_id", "value": case_id}},
            {"op": "in", "content": {"field": "data_format", "value": ["SVS"]}},
        ],
    }
    r = requests.get(GDC_FILES, params={
        "filters": json.dumps(filters),
        "format": "json",
        "fields": "file_id,file_name,file_size,experimental_strategy",
        "size": 100,
    }, timeout=60)
    r.raise_for_status()
    return r.json()["data"]["hits"]


def main() -> int:
    existing = existing_case_submitters()
    print(f"[1/3] Already on disk: {len(existing)} cases — {sorted(existing)}")

    print(f"[2/3] Fetching TCGA-COAD cases with pathology reports…")
    report_files = fetch_path_report_cases()
    print(f"      {len(report_files)} report files found")

    cases: list[dict] = []
    seen: set[str] = set()
    for f in report_files:
        for c in f.get("cases", []):
            sub = c.get("submitter_id", "")
            if not sub or sub in seen or sub in existing:
                continue
            seen.add(sub)
            dx = (c.get("diagnoses") or [{}])[0]
            cases.append({
                "submitter_id": sub,
                "case_id": c["case_id"],
                "report_file_id": f["file_id"],
                "report_file_name": f["file_name"],
                "gt": {
                    "primary_diagnosis": dx.get("primary_diagnosis"),
                    "tumor_grade": dx.get("tumor_grade"),
                    "stage": dx.get("ajcc_pathologic_stage"),
                    "pT": dx.get("ajcc_pathologic_t"),
                    "pN": dx.get("ajcc_pathologic_n"),
                    "pM": dx.get("ajcc_pathologic_m"),
                    "morphology": dx.get("morphology"),
                    "site": dx.get("site_of_resection_or_biopsy"),
                },
            })

    print(f"[3/3] Resolving slides per case (need {N_CASES})…")
    selected: list[dict] = []
    for case in cases:
        slides = fetch_slides_for_case(case["case_id"])
        # Need at least one DX slide for the pipeline to be meaningful
        has_dx = any("-DX" in s["file_name"].upper() for s in slides)
        if not has_dx or len(slides) < 1:
            continue
        case["slides"] = [
            {"file_id": s["file_id"], "file_name": s["file_name"],
             "size_mb": round(s["file_size"] / 1024 / 1024, 1)}
            for s in slides
        ]
        case["total_size_gb"] = round(sum(s["file_size"] for s in slides) / 1024**3, 2)
        selected.append(case)
        print(f"   + {case['submitter_id']}: {len(slides)} slides, {case['total_size_gb']} GB")
        if len(selected) >= N_CASES:
            break

    if len(selected) < N_CASES:
        print(f"WARN: only found {len(selected)}/{N_CASES} cases")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"cases": selected, "n": len(selected)}, indent=2))
    total_gb = sum(c["total_size_gb"] for c in selected)
    print(f"\nWrote {OUT}")
    print(f"Total download size: {total_gb:.1f} GB across {len(selected)} cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
