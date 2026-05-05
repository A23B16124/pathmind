"""
Hallucination guard — post-hoc validators for the Chief report.

Runs AFTER the pipeline finishes and produces a list of `Warning` objects
that get attached to the report payload. Frontend renders a banner per warning.

This is *not* a way to fix hallucinations — it surfaces them so the human
pathologist sees what to verify before signing the CAP report. Patient safety > confidence inflation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any, Iterable

from backend.schemas.agents import (
    ChiefOutput,
    HistopathologistOutput,
    LiteratureHunterOutput,
    TileTriageOutput,
)

# ──────────────────────────────────────────────────────────────────────────────
#  Validators
# ──────────────────────────────────────────────────────────────────────────────

# ICD-O-3 morphology code: 4 digits / behaviour digit (0-3, 6, 9)
_ICDO_RE = re.compile(r"^\d{4}/[0-369]$")

# pT(X|is|0-4)(a-d)? · pN(X|0-3)(a-c)? · pM(X|0-1)(a-c)?  — case-insensitive
_PT_RE = re.compile(r"^p?[Tt](?:X|is|[0-4])[a-d]?$", re.IGNORECASE)
_PN_RE = re.compile(r"^p?[Nn](?:X|[0-3])[a-c]?$", re.IGNORECASE)
_PM_RE = re.compile(r"^p?[Mm](?:X|[0-1])[a-c]?$", re.IGNORECASE)

# Common pancreas/breast IHC biomarkers we accept without flagging.
# This is intentionally permissive — only flag obvious nonsense.
_KNOWN_BIOMARKERS = {
    # Pancreas / GI
    "synaptophysin", "synaptophysine", "chromogranin", "chromogranine",
    "igg4", "ki-67", "ki67", "ck7", "ck19", "ck20", "muc1", "muc2", "muc5ac",
    "p53", "p16", "smad4", "dpc4", "kras", "cdx2",
    # Breast
    "er", "pr", "her2", "her2/neu", "ki-67", "e-cadherin", "ecad", "p120",
    "gata3", "mammaglobin", "gcdfp-15", "topoisomerase",
    # General
    "cd3", "cd4", "cd8", "cd20", "cd68", "cd138", "vimentin", "s100",
    "smooth muscle actin", "sma", "desmin",
}


@dataclass
class Warning_:
    """A single hallucination/safety flag attached to the report."""
    code: str           # short slug e.g. "icd_o_invalid"
    severity: str       # "info" | "warn" | "danger"
    message: str        # one-line explanation in French
    evidence: str = ""  # offending value


def _w(code: str, severity: str, message: str, evidence: str = "") -> Warning_:
    return Warning_(code=code, severity=severity, message=message, evidence=str(evidence)[:160])


# ──────────────────────────────────────────────────────────────────────────────
#  Individual checks
# ──────────────────────────────────────────────────────────────────────────────

def _check_icdo(cap: dict) -> list[Warning_]:
    code = (cap.get("icd_o_code") or "").strip()
    if not code:
        return []
    if not _ICDO_RE.match(code):
        return [_w("icd_o_invalid", "danger",
                   "Code ICD-O-3 mal formé. Format attendu : 4 chiffres / 1 comportement (ex 8550/3).",
                   code)]
    return []


def _check_tnm(cap: dict) -> list[Warning_]:
    out: list[Warning_] = []
    for key, regex, label in [
        ("pt_stage", _PT_RE, "pT"),
        ("pn_stage", _PN_RE, "pN"),
        ("pm_stage", _PM_RE, "pM"),
    ]:
        v = (cap.get(key) or "").strip()
        if v and not regex.match(v):
            out.append(_w(f"tnm_invalid_{key}", "warn",
                          f"Stade {label} mal formé.", v))
    return out


def _check_pmids(literature: LiteratureHunterOutput) -> list[Warning_]:
    """All papers in used_papers/suggested_papers must come from the RAG hits.
    By construction the agent now resolves them via by_ref, so a non-empty
    paper without a URL is suspicious."""
    out: list[Warning_] = []
    for label, papers in [("citée", literature.used_papers),
                          ("suggérée", literature.suggested_papers)]:
        for p in papers:
            if p.title and not p.url:
                out.append(_w("pmid_unverified", "warn",
                              f"Référence {label} sans lien source — vérifier le PMID/case_id.",
                              p.title[:80]))
            if p.pmid and len(p.pmid) > 0 and not (p.pmid.isdigit() or p.pmid.startswith("TCGA-")):
                out.append(_w("pmid_malformed", "warn",
                              "Identifiant de référence non standard.",
                              p.pmid))
    return out


def _check_slide_refs(report_dict: dict, n_slides: int) -> list[Warning_]:
    """Findings text must not reference slide indices outside [1, n_slides].
    We scan key_findings, debate_summary, recommendations for 'slide N' mentions."""
    if n_slides <= 0:
        return []
    text_blobs: list[str] = []
    cap = report_dict.get("cap_report") or {}
    if cap.get("debate_summary"):  text_blobs.append(str(cap["debate_summary"]))
    if cap.get("key_findings"):
        text_blobs.extend(str(x) for x in cap["key_findings"])
    if report_dict.get("debate_summary"):
        text_blobs.append(str(report_dict["debate_summary"]))

    bad_indices: set[int] = set()
    for blob in text_blobs:
        for m in re.finditer(r"(?:slide|lame|S-?)\s*0?(\d{1,3})", blob, re.IGNORECASE):
            idx = int(m.group(1))
            if idx < 1 or idx > n_slides:
                bad_indices.add(idx)
    if bad_indices:
        return [_w("slide_ref_oob", "danger",
                   f"Référence à des lames hors plage (1..{n_slides}).",
                   ", ".join(map(str, sorted(bad_indices))))]
    return []


def _check_quantitative_claims(report_dict: dict, max_patches_seen: int) -> list[Warning_]:
    """LLMs love to invent precise integers for mitotic counts, % necrosis, etc.
    We don't reject them — we surface a 'verify' flag because the model
    only saw `max_patches_seen` patches per slide, not a full-field count."""
    cap = report_dict.get("cap_report") or {}
    blobs = [str(cap.get("debate_summary") or "")]
    blobs.extend(str(x) for x in (cap.get("key_findings") or []))
    blobs.append(str(report_dict.get("debate_summary") or ""))

    flags: set[str] = set()
    for blob in blobs:
        if re.search(r"\b\d+\s*mitos", blob, re.IGNORECASE):
            flags.add("mitotic_count")
        if re.search(r"nécrose\s+\d+\s*%|necrosis\s+\d+\s*%", blob, re.IGNORECASE):
            flags.add("necrosis_pct")
        if re.search(r"\bR[01]\b.*?\d+[,\.]?\d*\s*mm", blob):
            flags.add("margin_mm")
        if re.search(r"Ki-?67\s*[:=]?\s*\d+\s*%", blob, re.IGNORECASE):
            flags.add("ki67_pct")

    out: list[Warning_] = []
    if "mitotic_count" in flags:
        out.append(_w("quant_mitotic", "warn",
                      f"Compte mitotique cité — modèle n'a vu que {max_patches_seen} patch(es) par lame, "
                      "valeur à vérifier sur lame entière.", "/HPF"))
    if "necrosis_pct" in flags:
        out.append(_w("quant_necrosis", "warn",
                      "% de nécrose chiffré — non quantifié par mesure de surface.", "%"))
    if "margin_mm" in flags:
        out.append(_w("quant_margin", "warn",
                      "Distance de marge en mm citée — non mesurée par étalonnage µm/px.", "mm"))
    if "ki67_pct" in flags:
        out.append(_w("quant_ki67", "warn",
                      "Index Ki-67 cité — vérifier par IHC réelle, le modèle ne fait pas de comptage cellulaire.", "%"))
    return out


def _check_biomarkers(biomarkers: Iterable[str]) -> list[Warning_]:
    out: list[Warning_] = []
    for b in biomarkers or []:
        slug = re.sub(r"[^a-z0-9]+", "", b.lower())
        if not slug:
            continue
        if not any(slug == re.sub(r"[^a-z0-9]+", "", k.lower()) for k in _KNOWN_BIOMARKERS):
            out.append(_w("biomarker_unknown", "info",
                          f"Biomarqueur non reconnu — vérifier l'orthographe IHC.",
                          b))
    return out


def _check_confidence_calibration(
    report: ChiefOutput,
    triage: list[TileTriageOutput],
    histo_a: list[HistopathologistOutput],
    histo_b: list[HistopathologistOutput],
) -> list[Warning_]:
    """Confidence > 0.85 is suspect when:
    - any triage parsed_failed, or
    - histo-A and histo-B both reported confidence < 0.5, or
    - more than 50% of slides failed.
    """
    out: list[Warning_] = []
    n = len(triage)
    failed = sum(1 for t in triage if t.parse_failed)
    weak_reads = sum(1 for r in histo_a + histo_b if r.confidence < 0.5)

    if report.confidence > 0.85 and failed > 0:
        out.append(_w("conf_overstated_triage", "danger",
                      f"Confiance {report.confidence:.2f} alors que {failed}/{n} lame(s) n'ont pas été analysées.",
                      f"{failed}/{n}"))
    if report.confidence > 0.85 and weak_reads >= n:
        out.append(_w("conf_overstated_reads", "warn",
                      "Confiance élevée malgré des lectures Histo-A/Histo-B faibles."))
    if n > 0 and failed / n > 0.5:
        out.append(_w("majority_failed", "danger",
                      f"Plus de la moitié des lames ont échoué ({failed}/{n}). Diagnostic non fiable.",
                      f"{failed}/{n}"))
    return out


def _check_diagnosis_when_all_failed(
    report: ChiefOutput, triage: list[TileTriageOutput],
) -> list[Warning_]:
    if not triage:
        return []
    if all(t.parse_failed for t in triage) and report.diagnosis.strip():
        return [_w("dx_without_evidence", "danger",
                   "Diagnostic produit alors qu'aucune lame n'a pu être analysée — à rejeter.",
                   report.diagnosis[:80])]
    return []


# ──────────────────────────────────────────────────────────────────────────────
#  Public entrypoint
# ──────────────────────────────────────────────────────────────────────────────

def audit_report(
    report: ChiefOutput,
    literature: LiteratureHunterOutput,
    triage: list[TileTriageOutput],
    histo_a: list[HistopathologistOutput],
    histo_b: list[HistopathologistOutput],
    *,
    max_patches_seen: int = 4,
) -> list[dict]:
    """
    Run every validator and return a list of warning dicts ready to JSON-serialize
    into the WS payload + the PDF/DOCX exports.
    """
    cap = report.cap_report or {}
    report_dict = {
        "diagnosis":     report.diagnosis,
        "biomarkers":    report.biomarkers,
        "debate_summary": report.debate_summary,
        "cap_report":    cap,
    }
    n_slides = len(triage)

    warnings: list[Warning_] = []
    warnings.extend(_check_icdo(cap))
    warnings.extend(_check_tnm(cap))
    warnings.extend(_check_pmids(literature))
    warnings.extend(_check_slide_refs(report_dict, n_slides))
    warnings.extend(_check_quantitative_claims(report_dict, max_patches_seen))
    warnings.extend(_check_biomarkers(report.biomarkers))
    warnings.extend(_check_confidence_calibration(report, triage, histo_a, histo_b))
    warnings.extend(_check_diagnosis_when_all_failed(report, triage))

    return [asdict(w) for w in warnings]
