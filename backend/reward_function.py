"""
Reward function for PPO training of the Chief agent.

Inputs:
  - pred: Chief's structured output (diagnosis, pt, pn, biomarkers, grade)
  - truth: ground truth from GDC clinical data

Output: scalar reward in [0.0, 1.0] (clipped from raw [-1, 1.5] for stability)

Components (weighted sum):
  - dx concordance (0.40): token-overlap match on primary diagnosis
  - pT concordance  (0.20): exact match pT0/T1/T2/T3/T4
  - pN concordance  (0.15): exact match pN0/N1/N2
  - grade concordance (0.10): G1/G2/G3 match
  - biomarker recall (0.10): how many recommended biomarkers are correct
  - organ_penalty   (0.05): −1.0 if breast diagnosed without breast context

Used by ppo_chief_reward.py (TRL PPOTrainer reward callback).
"""
import re
from typing import Any

def _normalize_dx(s: str) -> set[str]:
    if not s: return set()
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return set(re.sub(r"\s+", " ", s).strip().split())

def _norm_pt(s: str) -> str:
    m = re.search(r"\bpT([0-4][a-c]?)\b", s or "", re.IGNORECASE)
    return f"pT{m.group(1).upper()}" if m else ""

def _norm_pn(s: str) -> str:
    m = re.search(r"\bpN([0-3][a-c]?|x)\b", s or "", re.IGNORECASE)
    return f"pN{m.group(1).upper()}" if m else ""

def _norm_grade(s: str) -> str:
    if not s: return ""
    m = re.search(r"\bG\s*([1-4])\b|\b(I{1,3}V?)\b", s, re.IGNORECASE)
    if m and m.group(1): return f"G{m.group(1)}"
    if m and m.group(2):
        return {"I":"G1","II":"G2","III":"G3","IV":"G4"}.get(m.group(2).upper(), "")
    return ""

def _slug(x: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (x or "").lower())

def compute_reward(pred: dict, truth: dict, clinical_context: str = "") -> dict:
    """
    Returns dict: {reward: float, components: {...}, organ_hallucination: bool}
    """
    p_dx = pred.get("diagnosis") or pred.get("primary_diagnosis") or ""
    t_dx = truth.get("primary_diagnosis", "")
    p_tokens = _normalize_dx(p_dx)
    t_tokens = _normalize_dx(t_dx)
    if t_tokens:
        overlap = len(p_tokens & t_tokens)
        dx_score = min(1.0, overlap / max(1, len(t_tokens) - 1))
    else:
        dx_score = 0.0

    pt_score = 1.0 if (_norm_pt(pred.get("pt", "")) and _norm_pt(pred.get("pt", "")) == _norm_pt(truth.get("pt_stage", ""))) else 0.0
    pn_score = 1.0 if (_norm_pn(pred.get("pn", "")) and _norm_pn(pred.get("pn", "")) == _norm_pn(truth.get("pn_stage", ""))) else 0.0
    grade_score = 1.0 if (_norm_grade(pred.get("grade", "")) and _norm_grade(pred.get("grade", "")) == _norm_grade(truth.get("tumor_grade", ""))) else 0.0

    pred_bm = {_slug(b) for b in pred.get("biomarkers", []) if isinstance(b, str)}
    truth_bm = {_slug(b) for b in truth.get("biomarkers", []) if isinstance(b, str)}
    if truth_bm:
        bm_score = len(pred_bm & truth_bm) / len(truth_bm)
    else:
        bm_score = 0.5  # neutral if no truth biomarkers

    # Organ hallucination penalty
    organ_hallucination = False
    breast_terms = {"ductal", "idc", "breast", "lobular"}
    if any(t in p_dx.lower() for t in breast_terms):
        if "breast" not in clinical_context.lower() and "breast" not in t_dx.lower():
            organ_hallucination = True

    weighted = (
        0.40 * dx_score +
        0.20 * pt_score +
        0.15 * pn_score +
        0.10 * grade_score +
        0.10 * bm_score
    )
    if organ_hallucination:
        weighted -= 0.50  # hard penalty

    reward = max(0.0, min(1.0, weighted))

    return {
        "reward": reward,
        "components": {
            "dx_score":     round(dx_score, 3),
            "pt_score":     pt_score,
            "pn_score":     pn_score,
            "grade_score":  grade_score,
            "biomarker_score": round(bm_score, 3),
            "organ_hallucination_penalty": -0.50 if organ_hallucination else 0.0,
        },
        "organ_hallucination": organ_hallucination,
    }


if __name__ == "__main__":
    # Quick self-test
    import json, sys
    pred = {"diagnosis": "Colon adenocarcinoma", "pt": "pT3", "pn": "pN1",
            "grade": "G2", "biomarkers": ["KRAS", "MSI"]}
    truth = {"primary_diagnosis": "Colon adenocarcinoma", "pt_stage": "pT3",
             "pn_stage": "pN1", "tumor_grade": "G2", "biomarkers": ["KRAS", "MSI", "BRAF"]}
    r = compute_reward(pred, truth, clinical_context="Colon")
    print("Good case:")
    print(json.dumps(r, indent=2))

    pred_hall = {"diagnosis": "Invasive ductal carcinoma of no special type", "pt": "pT2", "pn": "pN0",
                 "grade": "G3", "biomarkers": ["ER", "PR", "HER2"]}
    r2 = compute_reward(pred_hall, truth, clinical_context="Colon")
    print("\nHallucination case:")
    print(json.dumps(r2, indent=2))
