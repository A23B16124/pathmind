"""
For each case in ground_truth.json:
  1. POST /api/cases to start a new analysis with the case's slides
  2. Poll for completion
  3. Compare PathMind output vs ground truth
  4. Aggregate concordance metrics

Output: data/benchmark/results.json + a console table.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests

API = "http://localhost:8011"
GT = Path("/root/pathmind/data/benchmark/ground_truth.json")
MANIFEST = Path("/root/pathmind/data/benchmark/manifest.json")
RESULTS = Path("/root/pathmind/data/benchmark/results.json")
SLIDE_DIR_PATH = "tcga"  # relative path the backend uses
POLL_INTERVAL = 10  # seconds
MAX_WAIT = 1800     # 30 min per case


def normalize_dx(s: str | None) -> str:
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def diagnosis_match(pred: str | None, truth: str | None) -> dict:
    """Token-overlap match — handles 'Adenocarcinoma' vs 'Colon adenocarcinoma'."""
    p = set(normalize_dx(pred).split())
    t = set(normalize_dx(truth).split())
    if not t:
        return {"match": None, "overlap": 0, "expected_tokens": 0}
    overlap = len(p & t)
    return {
        "match": overlap >= max(1, len(t) - 1),  # allow 1 missing token
        "overlap": overlap,
        "expected_tokens": len(t),
        "pred": pred, "truth": truth,
    }


def grade_match(pred: str | None, truth: str | None) -> dict:
    """G1/G2/G3 normalization."""
    def norm(s: str | None) -> str:
        if not s:
            return ""
        m = re.search(r"\bG\s*([1-4Xx])\b|\b(I{1,3}V?)\b", s, re.IGNORECASE)
        if not m:
            return s.lower().strip()
        if m.group(1):
            return f"G{m.group(1).upper()}"
        roman = m.group(2).upper()
        return {"I": "G1", "II": "G2", "III": "G3", "IV": "G4"}.get(roman, roman)

    np_, nt = norm(pred), norm(truth)
    return {"match": (np_ == nt and bool(nt)), "pred": pred, "truth": truth}


def stage_match(pred: str | None, truth: str | None) -> dict:
    """Compare stage roman numerals (loose — drop a/b suffix)."""
    def base(s: str | None) -> str:
        if not s:
            return ""
        m = re.search(r"\bStage\s*(I{1,3}V?|[1-4])[A-Ca-c]?\b", s, re.IGNORECASE)
        if m:
            return m.group(1).upper()
        return s.upper().strip()

    return {"match": (base(pred) == base(truth) and bool(base(truth))),
            "pred": pred, "truth": truth}


def biomarker_overlap(pred: list[str], truth: list[str]) -> dict:
    def slug(x: str) -> str:
        return re.sub(r"[^a-z0-9]", "", x.lower())
    p = {slug(x) for x in (pred or [])}
    t = {slug(x) for x in (truth or [])}
    if not t:
        return {"recall": None, "found": [], "missing": []}
    inter = p & t
    return {
        "recall": round(len(inter) / len(t), 2),
        "found": sorted([x for x in (truth or []) if slug(x) in inter]),
        "missing": sorted([x for x in (truth or []) if slug(x) not in inter]),
    }


def start_case(submitter_id: str, slide_files: list[str]) -> str:
    """POST /api/cases with the slide paths. Returns case_id."""
    paths = [f"{SLIDE_DIR_PATH}/{name}" for name in slide_files]
    payload = {
        "case_label": f"bench-{submitter_id}",
        "slides": paths,
    }
    r = requests.post(f"{API}/api/cases", json=payload, timeout=30)
    r.raise_for_status()
    return r.json()["case_id"]


def poll_case(case_id: str) -> dict:
    """Poll until report is ready or timeout."""
    t0 = time.time()
    while time.time() - t0 < MAX_WAIT:
        r = requests.get(f"{API}/api/cases/{case_id}/report", timeout=30)
        if r.status_code == 200:
            data = r.json()
            if data.get("status") == "complete" or data.get("report"):
                return data
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"case {case_id} did not finish in {MAX_WAIT}s")


def main() -> int:
    gt = json.loads(GT.read_text())
    manifest = json.loads(MANIFEST.read_text())
    case_index = {c["submitter_id"]: c for c in manifest["cases"]}

    results = {}
    for sub, gt_entry in gt.items():
        print(f"\n=== {sub} ===")
        case_meta = case_index.get(sub)
        if not case_meta:
            print("  [skip] not in manifest")
            continue
        slide_files = [s["file_name"] for s in case_meta["slides"]]
        try:
            case_id = start_case(sub, slide_files)
            print(f"  case_id={case_id}, polling…")
            data = poll_case(case_id)
        except Exception as e:
            print(f"  [ERR] {e}")
            results[sub] = {"error": str(e)}
            continue

        report = data.get("report") or data.get("cap_report") or {}
        pred = {
            "diagnosis": report.get("diagnosis") or data.get("diagnosis"),
            "grade": (report.get("cap_report") or {}).get("tumor_grade") or report.get("tumor_grade"),
            "stage": (report.get("cap_report") or {}).get("pt_stage") or report.get("pt_stage"),
            "biomarkers": report.get("biomarkers", []) or data.get("biomarkers", []),
            "confidence": report.get("confidence") or data.get("confidence"),
        }
        truth = gt_entry["structured"]
        truth_biomarkers = gt_entry["from_pdf"].get("biomarkers", [])

        cmp = {
            "diagnosis": diagnosis_match(pred["diagnosis"], truth.get("primary_diagnosis")),
            "grade": grade_match(pred["grade"], truth.get("tumor_grade")),
            "stage": stage_match(pred["stage"], truth.get("stage")),
            "biomarkers": biomarker_overlap(pred["biomarkers"], truth_biomarkers),
            "confidence": pred["confidence"],
        }
        results[sub] = {"pred": pred, "truth": truth, "cmp": cmp}
        print(f"  dx_match={cmp['diagnosis']['match']} "
              f"grade_match={cmp['grade']['match']} "
              f"stage_match={cmp['stage']['match']} "
              f"biomarker_recall={cmp['biomarkers']['recall']}")

    # Aggregate
    n = len(results)
    dx_ok = sum(1 for r in results.values() if r.get("cmp", {}).get("diagnosis", {}).get("match"))
    grade_ok = sum(1 for r in results.values() if r.get("cmp", {}).get("grade", {}).get("match"))
    stage_ok = sum(1 for r in results.values() if r.get("cmp", {}).get("stage", {}).get("match"))
    recalls = [r["cmp"]["biomarkers"]["recall"] for r in results.values()
               if r.get("cmp", {}).get("biomarkers", {}).get("recall") is not None]
    avg_recall = round(sum(recalls) / len(recalls), 2) if recalls else None

    summary = {
        "n_cases": n,
        "diagnosis_concordance": f"{dx_ok}/{n}",
        "grade_concordance": f"{grade_ok}/{n}",
        "stage_concordance": f"{stage_ok}/{n}",
        "avg_biomarker_recall": avg_recall,
    }
    print("\n" + "=" * 60)
    print("BENCHMARK SUMMARY")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    RESULTS.write_text(json.dumps({"summary": summary, "cases": results},
                                  indent=2, ensure_ascii=False))
    print(f"\nWrote {RESULTS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
