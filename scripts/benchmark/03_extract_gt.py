"""
Build ground_truth.json by combining:
  1. GDC clinical metadata (already in manifest.json, structured)
  2. Pathology report PDF text (free-form, parsed for biomarkers/margins)

The structured GDC fields are the trusted ground truth for diagnosis/grade/stage.
The PDF text adds biomarkers (IHC), margin status, and verbatim findings.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    print("Install: pip install pdfplumber", file=sys.stderr)
    sys.exit(1)

MANIFEST = Path("/root/pathmind/data/benchmark/manifest.json")
REPORT_DIR = Path("/root/pathmind/data/benchmark/reports")
OUT = Path("/root/pathmind/data/benchmark/ground_truth.json")

BIOMARKER_TOKENS = [
    "MLH1", "MSH2", "MSH6", "PMS2",
    "CK7", "CK20", "CDX2", "CEA",
    "p53", "Ki-67", "Ki67", "MIB-1",
    "Synaptophysin", "Chromogranin", "Synaptophysine",
    "HER2", "ER", "PR",
    "CD3", "CD8", "CD20", "CD117", "DOG1",
    "EMA", "S100", "Vimentin", "Desmin",
    "MUC2", "MUC5AC", "MUC1",
    "BRAF", "KRAS", "NRAS",
]

MARGIN_RE = re.compile(r"\bmargin[s]?\b.{0,80}\b(positive|negative|free|involved|clear|R0|R1|R2)\b",
                       re.IGNORECASE | re.DOTALL)
LVI_RE = re.compile(r"lymph[ovascular\s\-]*invasion.{0,40}\b(present|absent|positive|negative|yes|no|identified|not\s+identified)\b",
                    re.IGNORECASE | re.DOTALL)
PNI_RE = re.compile(r"perineural\s+invasion.{0,40}\b(present|absent|positive|negative|yes|no|identified|not\s+identified)\b",
                    re.IGNORECASE | re.DOTALL)
LN_RE = re.compile(r"(\d+)\s*[/\\]\s*(\d+)\s*lymph\s*nodes", re.IGNORECASE)


def extract_pdf_text(pdf: Path) -> str:
    if not pdf.exists():
        return ""
    try:
        with pdfplumber.open(pdf) as doc:
            return "\n".join((page.extract_text() or "") for page in doc.pages)
    except Exception as e:
        print(f"  [WARN] {pdf.name}: {e}")
        return ""


def parse_report(text: str) -> dict:
    if not text:
        return {"biomarkers": [], "raw_text_len": 0}

    biomarkers = []
    seen = set()
    for tok in BIOMARKER_TOKENS:
        if re.search(rf"\b{re.escape(tok)}\b", text, re.IGNORECASE):
            slug = tok.lower()
            if slug not in seen:
                biomarkers.append(tok)
                seen.add(slug)

    margin = None
    m = MARGIN_RE.search(text)
    if m:
        margin = m.group(1).lower()

    lvi = None
    m = LVI_RE.search(text)
    if m:
        lvi = m.group(1).lower()

    pni = None
    m = PNI_RE.search(text)
    if m:
        pni = m.group(1).lower()

    ln_pos = ln_total = None
    m = LN_RE.search(text)
    if m:
        ln_pos, ln_total = int(m.group(1)), int(m.group(2))

    return {
        "biomarkers": biomarkers,
        "margin_status": margin,
        "lymphovascular_invasion": lvi,
        "perineural_invasion": pni,
        "lymph_nodes_positive": ln_pos,
        "lymph_nodes_total": ln_total,
        "raw_text_len": len(text),
    }


def main() -> int:
    manifest = json.loads(MANIFEST.read_text())
    out = {}
    for case in manifest["cases"]:
        sub = case["submitter_id"]
        pdf = REPORT_DIR / f"{sub}.pdf"
        text = extract_pdf_text(pdf)
        parsed = parse_report(text)
        out[sub] = {
            "submitter_id": sub,
            "case_id": case["case_id"],
            "structured": case["gt"],
            "from_pdf": parsed,
            "n_slides": len(case["slides"]),
            "report_pdf": pdf.name if pdf.exists() else None,
        }
        print(f"[{sub}] dx={case['gt'].get('primary_diagnosis')!r} "
              f"grade={case['gt'].get('tumor_grade')!r} "
              f"stage={case['gt'].get('stage')!r} "
              f"biomarkers={len(parsed['biomarkers'])} "
              f"text={parsed['raw_text_len']}c")

    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"\nWrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
