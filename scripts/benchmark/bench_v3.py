"""Benchmark v3 — no clinical context, fixed prompts. Uses /api/analyze."""
from __future__ import annotations
import json, re, sys, time
from pathlib import Path
import requests

API = "http://localhost:8011"
GT   = Path("/root/pathmind/data/benchmark/ground_truth.json")
MANIFEST = Path("/root/pathmind/data/benchmark/manifest.json")
RESULTS  = Path("/root/pathmind/data/benchmark/results_v3.json")
SLIDE_DIR = "tcga"
POLL_INTERVAL = 10
MAX_WAIT = 1800

def normalize_dx(s):
    if not s: return ""
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def diagnosis_match(pred, truth):
    p = set(normalize_dx(pred).split())
    t = set(normalize_dx(truth).split())
    if not t: return {"match": None, "overlap": 0, "expected_tokens": 0, "pred": pred, "truth": truth}
    overlap = len(p & t)
    return {"match": overlap >= max(1, len(t) - 1), "overlap": overlap,
            "expected_tokens": len(t), "pred": pred, "truth": truth}

def grade_match(pred, truth):
    def norm(s):
        if not s: return ""
        m = re.search(r"\bG\s*([1-4Xx])\b|\b(I{1,3}V?)\b", s, re.IGNORECASE)
        if not m: return s.lower().strip()
        if m.group(1): return f"G{m.group(1).upper()}"
        return {"I":"G1","II":"G2","III":"G3","IV":"G4"}.get(m.group(2).upper(), m.group(2).upper())
    np_, nt = norm(pred), norm(truth)
    return {"match": np_ == nt and bool(nt), "pred": pred, "truth": truth}

def stage_match(pred, truth):
    def base(s):
        if not s: return ""
        m = re.search(r"\bStage\s*(I{1,3}V?|[1-4])[A-Ca-c]?\b", s, re.IGNORECASE)
        return m.group(1).upper() if m else s.upper().strip()
    return {"match": base(pred) == base(truth) and bool(base(truth)), "pred": pred, "truth": truth}

def pt_match(pred, truth):
    def norm(s):
        if not s: return ""
        m = re.search(r"\bpT([0-4][a-c]?)\b", s or "", re.IGNORECASE)
        return f"pT{m.group(1).upper()}" if m else ""
    return {"match": norm(pred) == norm(truth) and bool(norm(truth)), "pred": pred, "truth": truth}

def start_case(submitter_id, slide_files):
    paths = [f"{SLIDE_DIR}/{name}" for name in slide_files]
    payload = {"case_id": f"bench-v3-{submitter_id}", "patient_id": submitter_id, "slide_paths": paths}
    r = requests.post(f"{API}/api/analyze", json=payload, timeout=30)
    r.raise_for_status()
    return r.json()["case_id"]

def poll_case(case_id):
    t0 = time.time()
    while time.time() - t0 < MAX_WAIT:
        r = requests.get(f"{API}/api/case/{case_id}/report", timeout=30)
        if r.status_code == 200:
            data = r.json()
            if data.get("status") == "complete" or data.get("report"):
                return data
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"case {case_id} timed out")

def main():
    gt = json.loads(GT.read_text())
    manifest = json.loads(MANIFEST.read_text())
    case_index = {c["submitter_id"]: c for c in manifest["cases"]}
    results = {}

    for sub, gt_entry in gt.items():
        print(f"\n=== {sub} ===")
        case_meta = case_index.get(sub)
        if not case_meta:
            print("  [skip] not in manifest"); continue
        slide_files = [s["file_name"] for s in case_meta["slides"]]
        try:
            case_id = start_case(sub, slide_files)
            print(f"  case_id={case_id}, polling…")
            data = poll_case(case_id)
        except Exception as e:
            print(f"  [ERR] {e}")
            results[sub] = {"error": str(e)}; continue

        report = data.get("report") or {}
        synoptic = (report.get("cap_report") or {}).get("synoptic") or {}
        pred = {
            "diagnosis": report.get("diagnosis") or report.get("diagnosis_line"),
            "grade": synoptic.get("grade") or report.get("tumor_grade"),
            "pt": synoptic.get("pt") or report.get("pt_stage"),
            "confidence": report.get("confidence"),
        }
        truth = gt_entry["structured"]
        cmp = {
            "diagnosis": diagnosis_match(pred["diagnosis"], truth.get("primary_diagnosis")),
            "grade": grade_match(pred["grade"], truth.get("tumor_grade")),
            "pt": pt_match(pred["pt"], truth.get("pt_stage")),
            "confidence": pred["confidence"],
        }
        results[sub] = {"pred": pred, "truth": truth, "cmp": cmp}
        print(f"  dx={cmp['diagnosis']['match']} grade={cmp['grade']['match']} pT={cmp['pt']['match']}")
        print(f"  pred_dx: {(pred['diagnosis'] or '')[:90]}")

    n = len(results)
    dx_ok = sum(1 for r in results.values() if r.get("cmp",{}).get("diagnosis",{}).get("match"))
    grade_ok = sum(1 for r in results.values() if r.get("cmp",{}).get("grade",{}).get("match"))
    pt_ok = sum(1 for r in results.values() if r.get("cmp",{}).get("pt",{}).get("match"))
    summary = {"n_cases": n, "dx": f"{dx_ok}/{n}", "grade": f"{grade_ok}/{n}", "pt": f"{pt_ok}/{n}",
               "label": "v3 — no clinical context, fixed prompts"}
    print("\n" + "="*60)
    print("BENCHMARK V3 SUMMARY")
    for k, v in summary.items(): print(f"  {k}: {v}")
    RESULTS.write_text(json.dumps({"summary": summary, "cases": results}, indent=2, ensure_ascii=False))
    print(f"\nWrote {RESULTS}")

if __name__ == "__main__": sys.exit(main())
