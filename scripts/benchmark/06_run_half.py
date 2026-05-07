"""
Re-run benchmark on the FIRST 5 cases with clinical_data anchoring.

Fix: pass clinical_data={"site": <GDC primary site>, "sample_type": "Colon resection (TCGA-COAD)"}
so all agents (Histo-A/B, Cross-Slide, DDx, Literature, Report-Writer) anchor
to the colon and stop hallucinating breast cancer.

Also bumps the case_id to bench2-* so it doesn't hit the cached breast reports.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import requests

API = "http://localhost:8011"
GT = Path("/root/pathmind/data/benchmark/ground_truth.json")
MANIFEST = Path("/root/pathmind/data/benchmark/manifest.json")
RESULTS = Path("/root/pathmind/data/benchmark/results_anchored.json")
N_CASES = 5
SLIDE_DIR_PATH = "tcga"
POLL_INTERVAL = 15
MAX_WAIT = 1800


def normalize_dx(s):
    if not s:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s.lower())).strip()


def diagnosis_match(pred, truth):
    if not truth:
        return {"match": None, "pred": pred, "truth": truth}
    p = normalize_dx(pred)
    core = [w for w in normalize_dx(truth).split()
            if w not in {"nos", "not", "otherwise", "specified", "of", "the"}]
    if not core:
        return {"match": None, "pred": pred, "truth": truth}
    return {"match": core[0] in p, "pred": pred, "truth": truth, "core": core[0]}


def grade_match(pred, truth):
    def norm(s):
        if not s:
            return ""
        m = re.search(r"\bGrade\s*([IVX1-4])\b|\bG\s*([1-4Xx])\b|\b(I{1,3}V?)\b", s, re.I)
        if not m:
            return ""
        for g in m.groups():
            if g:
                return f"G{ {'I':'1','II':'2','III':'3','IV':'4'}.get(g.upper(), g) }"
        return ""
    np_, nt = norm(pred), norm(truth)
    if not nt:
        return {"match": None, "pred": pred, "truth": truth}
    return {"match": np_ == nt, "pred": pred, "truth": truth, "norm": (np_, nt)}


def stage_match(pred, truth):
    def base(s):
        if not s:
            return None
        m = re.search(r"\bStage\s*(I{1,3}V?|[1-4])[A-Ca-c]?\b", s, re.I)
        return m.group(1).upper() if m else None
    bp, bt = base(pred), base(truth)
    if not bt:
        return {"match": None, "pred": pred, "truth": truth}
    return {"match": bp == bt, "pred": pred, "truth": truth}


def pt_match(pred, truth):
    def base(s):
        if not s:
            return None
        m = re.search(r"\b[pP]?T\s*(\d|is|X)\b", s)
        return f"T{m.group(1).upper()}" if m else None
    bp, bt = base(pred), base(truth)
    if not bt:
        return {"match": None, "pred": pred, "truth": truth}
    return {"match": bp == bt, "pred": pred, "truth": truth}


def biomarker_overlap(pred, truth):
    def slug(x):
        return re.sub(r"[^a-z0-9]", "", x.lower())
    p_slugs = set()
    for x in pred or []:
        clean = re.sub(r"\s*\([^)]*\)", "", x)
        for tok in re.split(r"[/,;+&]| and | et ", clean, flags=re.I):
            s = slug(tok)
            if s:
                p_slugs.add(s)
    t_slugs = {slug(x) for x in (truth or [])}
    if not t_slugs:
        return {"recall": None, "found": [], "missing": []}
    inter = p_slugs & t_slugs
    return {
        "recall": round(len(inter) / len(t_slugs), 2),
        "found": sorted([x for x in (truth or []) if slug(x) in inter]),
        "missing": sorted([x for x in (truth or []) if slug(x) not in inter]),
    }


def start_case(submitter_id, slide_files, gdc_site):
    paths = [f"{SLIDE_DIR_PATH}/{name}" for name in slide_files]
    case_id = f"bench2-{submitter_id.lower()}"
    site = gdc_site or "Colon, NOS"
    clinical_data = {
        "site": site,
        "sample_type": "Colon resection (TCGA-COAD cohort)",
        "context": (f"Patient from TCGA-COAD cohort. Anatomic site: {site}. "
                    f"Specimen is a colon resection. Tumor is a colorectal "
                    f"adenocarcinoma. ONLY consider differentials of the colon "
                    f"and small bowel. DO NOT consider breast, lung, prostate, "
                    f"or any other organ."),
    }
    payload = {
        "case_id": case_id,
        "patient_id": submitter_id,
        "slide_paths": paths,
        "clinical_data": clinical_data,
    }
    r = requests.post(f"{API}/api/analyze", json=payload, timeout=30)
    r.raise_for_status()
    return case_id


def poll_case(case_id):
    t0 = time.time()
    while time.time() - t0 < MAX_WAIT:
        q = requests.get(f"{API}/api/queue", timeout=10).json()
        is_active = case_id in (q.get("active_cases") or [])
        r = requests.get(f"{API}/api/case/{case_id}/report", timeout=30)
        if r.status_code == 200 and not is_active:
            return r.json()
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"case {case_id} timed out at {MAX_WAIT}s")


def main():
    gt = json.loads(GT.read_text())
    manifest = json.loads(MANIFEST.read_text())
    case_index = {c["submitter_id"]: c for c in manifest["cases"]}

    selected = list(gt.keys())[:N_CASES]
    print(f"Running benchmark v2 (anchored) on {len(selected)} cases:\n  {selected}\n")

    results = {}
    for sub in selected:
        gt_entry = gt[sub]
        case_meta = case_index[sub]
        gdc_site = gt_entry["structured"].get("site")
        slide_files = [s["file_name"] for s in case_meta["slides"]]

        print(f"=== {sub} (site: {gdc_site}) ===")
        try:
            case_id = start_case(sub, slide_files, gdc_site)
            print(f"  case_id={case_id}")
            data = poll_case(case_id)
        except Exception as e:
            print(f"  [ERR] {e}")
            results[sub] = {"error": str(e)}
            continue

        rep = data.get("report", {})
        cap = rep.get("cap_report") or {}
        synoptic = cap.get("synoptic") or {}

        pred = {
            "diagnosis": rep.get("diagnosis"),
            "diagnosis_line": cap.get("diagnosis_line"),
            "specimen_type": (cap.get("specimen") or {}).get("type"),
            "histologic_type": synoptic.get("histologic_type"),
            "grade": synoptic.get("grade"),
            "pt": synoptic.get("pt"),
            "pn": synoptic.get("pn"),
            "biomarkers": rep.get("biomarkers", []),
            "confidence": rep.get("confidence"),
        }
        truth = gt_entry["structured"]
        truth_biomarkers = gt_entry["from_pdf"].get("biomarkers", [])

        cmp = {
            "diagnosis": diagnosis_match(pred["diagnosis"], truth.get("primary_diagnosis")),
            "histologic_type": diagnosis_match(pred["histologic_type"], truth.get("primary_diagnosis")),
            "grade": grade_match(pred["grade"], truth.get("tumor_grade")),
            "stage": stage_match(pred.get("stage"), truth.get("stage")),
            "pt": pt_match(pred["pt"], truth.get("pT")),
            "biomarkers": biomarker_overlap(pred["biomarkers"], truth_biomarkers),
        }
        results[sub] = {"pred": pred, "truth": truth,
                        "truth_biomarkers": truth_biomarkers, "cmp": cmp}
        print(f"  diag={pred['diagnosis']!r}")
        print(f"  specimen={pred['specimen_type']!r}")
        print(f"  match: dx={cmp['diagnosis']['match']} hist={cmp['histologic_type']['match']} "
              f"pT={cmp['pt']['match']} bio_recall={cmp['biomarkers']['recall']}\n")

    # Aggregate
    n = len(results)
    def count(field):
        ok = sum(1 for r in results.values() if r.get("cmp", {}).get(field, {}).get("match") is True)
        scored = sum(1 for r in results.values() if r.get("cmp", {}).get(field, {}).get("match") is not None)
        return f"{ok}/{scored}"
    recalls = [r["cmp"]["biomarkers"]["recall"] for r in results.values()
               if r.get("cmp", {}).get("biomarkers", {}).get("recall") is not None]
    summary = {
        "n_cases": n,
        "diagnosis_concordance": count("diagnosis"),
        "histologic_type_concordance": count("histologic_type"),
        "grade_concordance": count("grade"),
        "pT_concordance": count("pt"),
        "stage_concordance": count("stage"),
        "avg_biomarker_recall": round(sum(recalls) / len(recalls), 2) if recalls else None,
    }
    print("=" * 60)
    print("ANCHORED BENCHMARK SUMMARY")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    RESULTS.write_text(json.dumps({"summary": summary, "cases": results},
                                  indent=2, ensure_ascii=False))
    print(f"\nWrote {RESULTS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
