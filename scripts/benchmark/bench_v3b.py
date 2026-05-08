"""Benchmark v3b — skip AY-A71X (stalled), MAX_WAIT=600s."""
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
MAX_WAIT = 600  # 10 min max per case
SKIP = {"TCGA-AY-A71X"}  # stalled foundation model

def normalize_dx(s):
    if not s: return ""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s.lower())).strip()

def diagnosis_match(pred, truth):
    p = set(normalize_dx(pred).split())
    t = set(normalize_dx(truth).split())
    if not t: return {"match": None, "pred": pred, "truth": truth}
    overlap = len(p & t)
    return {"match": overlap >= max(1, len(t) - 1), "overlap": overlap, "pred": pred, "truth": truth}

def grade_match(pred, truth):
    def norm(s):
        if not s: return ""
        m = re.search(r"\bG\s*([1-4])\b|\b(I{1,3}V?)\b", s, re.IGNORECASE)
        if not m: return s.lower().strip()
        if m.group(1): return f"G{m.group(1)}"
        return {"I":"G1","II":"G2","III":"G3","IV":"G4"}.get(m.group(2).upper(), m.group(2).upper())
    np_, nt = norm(pred), norm(truth)
    return {"match": np_ == nt and bool(nt), "pred": pred, "truth": truth}

def pt_match(pred, truth):
    def norm(s):
        m = re.search(r"\bpT([0-4][a-c]?)\b", s or "", re.IGNORECASE)
        return f"pT{m.group(1).upper()}" if m else ""
    return {"match": norm(pred) == norm(truth) and bool(norm(truth)), "pred": pred, "truth": truth}

def start_case(sub, slides):
    paths = [f"{SLIDE_DIR}/{name}" for name in slides]
    r = requests.post(f"{API}/api/analyze", json={"case_id": f"bench-v3-{sub}", "patient_id": sub, "slide_paths": paths}, timeout=30)
    r.raise_for_status()
    return r.json()["case_id"]

def poll_case(case_id):
    t0 = time.time()
    while time.time() - t0 < MAX_WAIT:
        r = requests.get(f"{API}/api/case/{case_id}/report", timeout=30)
        if r.status_code == 200:
            d = r.json()
            if d.get("status") == "complete" or d.get("report"): return d
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"{case_id} timed out after {MAX_WAIT}s")

def main():
    gt = json.loads(GT.read_text())
    manifest = json.loads(MANIFEST.read_text())
    case_index = {c["submitter_id"]: c for c in manifest["cases"]}

    # Load existing partial results from v3
    existing = {}
    if RESULTS.exists():
        try:
            existing = json.loads(RESULTS.read_text()).get("cases", {})
        except: pass

    results = dict(existing)

    for sub, gt_entry in gt.items():
        if sub in SKIP:
            print(f"\n=== {sub} [SKIP — stalled] ===")
            results[sub] = {"error": "foundation-model stall, skipped"}
            continue
        if sub in results and "cmp" in results[sub]:
            print(f"\n=== {sub} [cached] dx={results[sub]['cmp']['diagnosis']['match']} ===")
            continue
        print(f"\n=== {sub} ===", flush=True)
        case_meta = case_index.get(sub)
        if not case_meta:
            print("  [skip] not in manifest"); continue
        slide_files = [s["file_name"] for s in case_meta["slides"]]
        try:
            case_id = start_case(sub, slide_files)
            print(f"  case_id={case_id}, polling…", flush=True)
            data = poll_case(case_id)
        except Exception as e:
            print(f"  [ERR] {e}", flush=True)
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
        }
        results[sub] = {"pred": pred, "truth": truth, "cmp": cmp}
        print(f"  dx={cmp['diagnosis']['match']} grade={cmp['grade']['match']} pT={cmp['pt']['match']}", flush=True)
        print(f"  pred: {(pred['diagnosis'] or '')[:90]}", flush=True)

        # Save incrementally
        _save(results)

    _save(results)
    _print_summary(results)

def _save(results):
    n = len(results)
    dx_ok = sum(1 for r in results.values() if r.get("cmp",{}).get("diagnosis",{}).get("match"))
    grade_ok = sum(1 for r in results.values() if r.get("cmp",{}).get("grade",{}).get("match"))
    pt_ok = sum(1 for r in results.values() if r.get("cmp",{}).get("pt",{}).get("match"))
    summary = {"n_cases": n, "dx": f"{dx_ok}/{n}", "grade": f"{grade_ok}/{n}", "pt": f"{pt_ok}/{n}",
               "label": "v3 — no clinical context, fixed prompts (organ-confirm step, no breast default)"}
    RESULTS.write_text(json.dumps({"summary": summary, "cases": results}, indent=2, ensure_ascii=False))

def _print_summary(results):
    n = len([r for r in results.values() if "cmp" in r])
    dx_ok = sum(1 for r in results.values() if r.get("cmp",{}).get("diagnosis",{}).get("match"))
    grade_ok = sum(1 for r in results.values() if r.get("cmp",{}).get("grade",{}).get("match"))
    pt_ok = sum(1 for r in results.values() if r.get("cmp",{}).get("pt",{}).get("match"))
    print(f"\n{'='*60}")
    print("BENCHMARK V3 SUMMARY")
    print(f"  cases evaluated: {n}/10")
    print(f"  dx:    {dx_ok}/{n}")
    print(f"  grade: {grade_ok}/{n}")
    print(f"  pT:    {pt_ok}/{n}")
    print(f"\nWrote {RESULTS}")

if __name__ == "__main__": sys.exit(main())
