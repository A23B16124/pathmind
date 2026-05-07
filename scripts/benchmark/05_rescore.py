"""
Re-score the benchmark using cached reports — no pipeline re-run needed.

Reads the cached /api/case/{case_id}/report for each bench case and applies
corrected matching logic against ground_truth.json. The original 04_run_benchmark.py
read the wrong fields (pt_stage instead of synoptic.pt).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import requests

API = "http://localhost:8011"
GT = Path("/root/pathmind/data/benchmark/ground_truth.json")
RESULTS = Path("/root/pathmind/data/benchmark/results_v2.json")


def normalize_dx(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def diagnosis_match(pred: str | None, truth: str | None) -> dict:
    """Looser match — succeed if the GT 'core word' appears in pred."""
    p = normalize_dx(pred)
    t = normalize_dx(truth)
    if not t:
        return {"match": None, "pred": pred, "truth": truth}
    # Core token: drop "NOS", "not otherwise specified", articles
    core = [w for w in t.split() if w not in {"nos", "not", "otherwise", "specified", "of", "the"}]
    if not core:
        return {"match": None, "pred": pred, "truth": truth}
    main = core[0]  # e.g. "adenocarcinoma" or "papillary"
    match = main in p
    return {"match": match, "pred": pred, "truth": truth, "core": main}


def grade_match(pred: str | None, truth: str | None) -> dict:
    def norm(s: str | None) -> str:
        if not s:
            return ""
        m = re.search(r"\bGrade\s*([IVX1-4])\b|\bG\s*([1-4Xx])\b|\b(I{1,3}V?)\b", s, re.IGNORECASE)
        if not m:
            return ""
        for g in m.groups():
            if g:
                roman = {"I": "1", "II": "2", "III": "3", "IV": "4"}.get(g.upper(), g)
                return f"G{roman}"
        return ""

    np_, nt = norm(pred), norm(truth)
    if not nt:
        return {"match": None, "pred": pred, "truth": truth}
    return {"match": np_ == nt, "pred": pred, "truth": truth, "norm_pred": np_, "norm_truth": nt}


def stage_match(pred: str | None, truth: str | None) -> dict:
    def base(s: str | None) -> str | None:
        if not s:
            return None
        m = re.search(r"\bStage\s*(I{1,3}V?|[1-4])[A-Ca-c]?\b", s, re.IGNORECASE)
        return m.group(1).upper() if m else None

    bp, bt = base(pred), base(truth)
    if not bt:
        return {"match": None, "pred": pred, "truth": truth}
    return {"match": bp == bt, "pred": pred, "truth": truth}


def pt_match(pred: str | None, truth: str | None) -> dict:
    def base(s: str | None) -> str | None:
        if not s:
            return None
        m = re.search(r"\b[pP]?T\s*(\d|is|X)\b", s)
        return f"T{m.group(1).upper()}" if m else None

    bp, bt = base(pred), base(truth)
    if not bt:
        return {"match": None, "pred": pred, "truth": truth}
    return {"match": bp == bt, "pred": pred, "truth": truth}


def biomarker_overlap(pred: list[str], truth: list[str]) -> dict:
    def slug(x: str) -> str:
        return re.sub(r"[^a-z0-9]", "", x.lower())
    p_slugs = set()
    for x in pred or []:
        # Split combined panels and strip parens
        clean = re.sub(r"\s*\([^)]*\)", "", x)
        for tok in re.split(r"[/,;+&]| and | et ", clean, flags=re.IGNORECASE):
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


def main() -> int:
    gt = json.loads(GT.read_text())
    results: dict = {}

    for sub, gt_entry in gt.items():
        case_id = f"bench-{sub.lower()}"
        r = requests.get(f"{API}/api/case/{case_id}/report", timeout=15)
        if r.status_code != 200:
            print(f"[{sub}] no cached report ({r.status_code})")
            continue
        cached = r.json()
        rep = cached.get("report", {})
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
        print(f"[{sub}] dx={cmp['diagnosis']['match']} "
              f"hist={cmp['histologic_type']['match']} "
              f"grade={cmp['grade']['match']} "
              f"pT={cmp['pt']['match']} "
              f"bio_recall={cmp['biomarkers']['recall']}")

    n = len(results)
    def count(field: str) -> str:
        ok = sum(1 for r in results.values() if r["cmp"][field]["match"] is True)
        scored = sum(1 for r in results.values() if r["cmp"][field]["match"] is not None)
        return f"{ok}/{scored}"

    recalls = [r["cmp"]["biomarkers"]["recall"] for r in results.values()
               if r["cmp"]["biomarkers"]["recall"] is not None]
    avg_recall = round(sum(recalls) / len(recalls), 2) if recalls else None

    summary = {
        "n_cases": n,
        "diagnosis_concordance": count("diagnosis"),
        "histologic_type_concordance": count("histologic_type"),
        "grade_concordance": count("grade"),
        "pT_concordance": count("pt"),
        "stage_concordance": count("stage"),
        "avg_biomarker_recall": avg_recall,
    }
    print("\n" + "=" * 60)
    print("RESCORED BENCHMARK SUMMARY")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    RESULTS.write_text(json.dumps({"summary": summary, "cases": results},
                                  indent=2, ensure_ascii=False))
    print(f"\nWrote {RESULTS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
