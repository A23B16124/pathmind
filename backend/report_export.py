"""
Report export — PDF (reportlab + DejaVu) and DOCX (python-docx).

Both renderers honour French accents (UTF-8 + DejaVu / native docx) and produce
a CAP-style anatomopathology report from the dict shape we send to the frontend.
"""

from __future__ import annotations

import io
from typing import Any

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, HRFlowable,
)


_FONTS_REGISTERED = False
_DEJAVU = "/usr/share/fonts/truetype/dejavu"


def _register_fonts() -> None:
    """Register DejaVu once. DejaVu Sans supports full Latin extended (accents)."""
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    pdfmetrics.registerFont(TTFont("DejaVu",       f"{_DEJAVU}/DejaVuSans.ttf"))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold",  f"{_DEJAVU}/DejaVuSans-Bold.ttf"))
    pdfmetrics.registerFont(TTFont("DejaVu-Italic", f"{_DEJAVU}/DejaVuSans-Oblique.ttf"))
    pdfmetrics.registerFont(TTFont("DejaVu-Mono",  f"{_DEJAVU}/DejaVuSansMono.ttf"))
    _FONTS_REGISTERED = True


# ──────────────────────────────────────────────────────────────────────────────
#  PDF
# ──────────────────────────────────────────────────────────────────────────────

INK         = HexColor("#1c1a16")
INK_SOFT    = HexColor("#4a4538")
MUTED       = HexColor("#807866")
RULE        = HexColor("#c8c1b1")
RULE_STRONG = HexColor("#5e574b")
ACCENT      = HexColor("#6b1d1d")
PAPER_2     = HexColor("#ebe6db")


def _pdf_styles() -> dict:
    base = getSampleStyleSheet()["Normal"]
    return {
        "title":  ParagraphStyle("title",  parent=base, fontName="DejaVu-Bold",
                                 fontSize=20, leading=24, textColor=INK, spaceAfter=4),
        "h2":     ParagraphStyle("h2",     parent=base, fontName="DejaVu-Bold",
                                 fontSize=12, leading=16, textColor=INK, spaceBefore=14, spaceAfter=4),
        "smcaps": ParagraphStyle("smcaps", parent=base, fontName="DejaVu-Mono",
                                 fontSize=8, leading=10, textColor=MUTED, spaceAfter=2),
        "body":   ParagraphStyle("body",   parent=base, fontName="DejaVu",
                                 fontSize=10, leading=14, textColor=INK, alignment=TA_LEFT, spaceAfter=4),
        "italic": ParagraphStyle("italic", parent=base, fontName="DejaVu-Italic",
                                 fontSize=10, leading=14, textColor=INK_SOFT, spaceAfter=4),
        "mono":   ParagraphStyle("mono",   parent=base, fontName="DejaVu-Mono",
                                 fontSize=9, leading=12, textColor=INK_SOFT),
        "accent": ParagraphStyle("accent", parent=base, fontName="DejaVu-Bold",
                                 fontSize=10, leading=14, textColor=ACCENT),
    }


def _kv_table(rows: list[tuple[str, str]], styles: dict) -> Table:
    """Small ICD/TNM/Margins grid."""
    data = [[Paragraph(k, styles["smcaps"]), Paragraph(v or "—", styles["body"])] for k, v in rows]
    t = Table(data, colWidths=[55 * mm, 110 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), PAPER_2),
        ("BOX",         (0, 0), (-1, -1), 0.5, RULE),
        ("INNERGRID",   (0, 0), (-1, -1), 0.25, RULE),
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",(0, 0), (-1, -1), 8),
        ("TOPPADDING",  (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
    ]))
    return t


def _papers_block(title: str, papers: list[dict], accent: bool, styles: dict) -> list:
    if not papers:
        return [Paragraph(f"{title} — aucun.", styles["italic"]), Spacer(1, 4)]
    flow = [Paragraph(title, styles["smcaps"]), Spacer(1, 2)]
    for p in papers:
        ref = p.get("pmid") or ""
        src = "TCGA" if p.get("source") == "tcga_case" else "PMID"
        head = f"<b>{src} {ref}</b> · τ {float(p.get('score', 0)):.2f} — {p.get('title', '')}"
        flow.append(Paragraph(head, styles["accent"] if accent else styles["body"]))
        meta = " · ".join(filter(None, [p.get("journal"), str(p.get("year") or ""), p.get("authors")]))
        if meta:
            flow.append(Paragraph(meta, styles["mono"]))
        if p.get("relevance"):
            flow.append(Paragraph(p["relevance"], styles["italic"]))
        if p.get("snippet"):
            flow.append(Paragraph(p["snippet"][:400], styles["body"]))
        if p.get("url"):
            flow.append(Paragraph(p["url"], styles["mono"]))
        flow.append(Spacer(1, 6))
    return flow


def render_pdf(report: dict[str, Any], patient_label: str = "") -> bytes:
    """Build a CAP-style PDF report. Returns the PDF as bytes."""
    _register_fonts()
    styles = _pdf_styles()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=22 * mm, bottomMargin=18 * mm,
        leftMargin=22 * mm, rightMargin=22 * mm,
        title="PathMind — Rapport CAP",
        author="PathMind v0.2",
    )

    cap = report.get("cap_report") or {}
    diagnosis = (cap.get("primary_diagnosis") or report.get("diagnosis")
                 or "Diagnostic indéterminé")
    icd       = str(cap.get("icd_o_code") or "—")
    tnm       = f"{cap.get('pt_stage','—')} {cap.get('pn_stage','')}".strip()
    margin    = str(cap.get("margin_status") or "—")
    pni       = str(cap.get("perineural_invasion") or "—")
    conf      = float(report.get("confidence") or 0)

    biomarkers = report.get("biomarkers") or cap.get("biomarkers") or []
    findings   = cap.get("key_findings") or []
    recos      = cap.get("recommendations") or report.get("recommendations") or []
    debate     = report.get("debate_summary") or cap.get("debate_summary")

    lit = report.get("literature") or {}
    used = lit.get("used_papers") or []
    suggested = lit.get("suggested_papers") or []

    story: list = []

    # Header band
    story.append(Paragraph("PathMind — Rapport CAP", styles["title"]))
    story.append(Paragraph(
        f"{patient_label or '—'} · v0.2 · confiance multi-agents τ {conf:.2f}",
        styles["mono"],
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=RULE_STRONG, spaceBefore=4, spaceAfter=10))

    # Diagnostic
    story.append(Paragraph("Diagnostic primaire", styles["smcaps"]))
    story.append(Paragraph(diagnosis, styles["h2"]))
    story.append(Spacer(1, 4))
    story.append(_kv_table([
        ("ICD-O-3",                        icd),
        ("Stade pTNM",                     tnm or "—"),
        ("Marges",                         margin),
        ("Engainement périnerveux",        pni),
    ], styles))
    story.append(Spacer(1, 12))

    if debate:
        story.append(Paragraph("Synthèse du débat", styles["smcaps"]))
        story.append(Paragraph(debate, styles["body"]))

    if biomarkers:
        story.append(Paragraph("Biomarqueurs IHC recommandés", styles["h2"]))
        story.append(Paragraph(" · ".join(biomarkers), styles["body"]))

    if findings:
        story.append(Paragraph("Constatations clés", styles["h2"]))
        for i, f in enumerate(findings, 1):
            story.append(Paragraph(f"{i}. {f}", styles["body"]))

    if recos:
        story.append(Paragraph("Recommandations cliniques", styles["h2"]))
        for r in recos:
            story.append(Paragraph(f"› {r}", styles["body"]))

    # Literature
    if used or suggested:
        story.append(Paragraph("Littérature", styles["h2"]))
        if lit.get("key_findings"):
            story.append(Paragraph(lit["key_findings"], styles["body"]))
            story.append(Spacer(1, 4))
        story.extend(_papers_block("Références citées par le Chief", used, accent=True, styles=styles))
        story.extend(_papers_block("Suggestions complémentaires",   suggested, accent=False, styles=styles))

    # Audit / hallucination warnings — surfaced at the end so the reviewer sees them
    warnings = report.get("warnings") or []
    if warnings:
        story.append(HRFlowable(width="100%", thickness=0.5, color=RULE_STRONG, spaceBefore=14, spaceAfter=6))
        story.append(Paragraph("Audit anti-hallucination", styles["h2"]))
        for w in warnings:
            sev = w.get("severity", "info")
            sev_label = {"danger": "À VÉRIFIER", "warn": "Attention", "info": "Info"}.get(sev, "Info")
            color = ACCENT if sev == "danger" else MUTED
            head = f'<font color="{color.hexval()}"><b>[{sev_label}]</b></font> {w.get("message", "")}'
            story.append(Paragraph(head, styles["body"]))
            if w.get("evidence"):
                story.append(Paragraph(f"→ {w['evidence']}", styles["mono"]))
            story.append(Spacer(1, 3))

    # Footer
    story.append(HRFlowable(width="100%", thickness=0.5, color=RULE, spaceBefore=14, spaceAfter=4))
    story.append(Paragraph(
        "Rapport généré automatiquement par PathMind. Diagnostic à valider par un anatomopathologiste habilité.",
        styles["italic"],
    ))

    doc.build(story)
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────────────────────
#  DOCX
# ──────────────────────────────────────────────────────────────────────────────

def render_docx(report: dict[str, Any], patient_label: str = "") -> bytes:
    """Build a CAP-style DOCX report. Returns the DOCX as bytes."""
    from docx import Document
    from docx.shared import Pt, RGBColor

    cap = report.get("cap_report") or {}
    diagnosis = cap.get("primary_diagnosis") or report.get("diagnosis") or "Diagnostic indéterminé"
    conf = float(report.get("confidence") or 0)

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)

    h = doc.add_heading("PathMind — Rapport CAP", level=0)
    doc.add_paragraph(f"{patient_label or '—'} · confiance multi-agents τ {conf:.2f}")

    doc.add_heading("Diagnostic primaire", level=1)
    doc.add_paragraph(diagnosis).runs[0].bold = True

    table = doc.add_table(rows=4, cols=2)
    table.style = "Light Grid Accent 1"
    rows = [
        ("ICD-O-3",                  str(cap.get("icd_o_code") or "—")),
        ("Stade pTNM",               f"{cap.get('pt_stage','—')} {cap.get('pn_stage','')}".strip() or "—"),
        ("Marges",                   str(cap.get("margin_status") or "—")),
        ("Engainement périnerveux",  str(cap.get("perineural_invasion") or "—")),
    ]
    for i, (k, v) in enumerate(rows):
        table.rows[i].cells[0].text = k
        table.rows[i].cells[1].text = v

    if report.get("debate_summary"):
        doc.add_heading("Synthèse du débat", level=1)
        doc.add_paragraph(report["debate_summary"])

    bm = report.get("biomarkers") or cap.get("biomarkers") or []
    if bm:
        doc.add_heading("Biomarqueurs IHC recommandés", level=1)
        doc.add_paragraph(" · ".join(bm))

    findings = cap.get("key_findings") or []
    if findings:
        doc.add_heading("Constatations clés", level=1)
        for f in findings:
            doc.add_paragraph(f, style="List Number")

    recos = cap.get("recommendations") or report.get("recommendations") or []
    if recos:
        doc.add_heading("Recommandations cliniques", level=1)
        for r in recos:
            doc.add_paragraph(r, style="List Bullet")

    lit = report.get("literature") or {}
    if lit.get("used_papers") or lit.get("suggested_papers"):
        doc.add_heading("Littérature", level=1)
        if lit.get("key_findings"):
            doc.add_paragraph(lit["key_findings"])
        for label, papers in [("Références citées par le Chief", lit.get("used_papers") or []),
                              ("Suggestions complémentaires",    lit.get("suggested_papers") or [])]:
            doc.add_heading(label, level=2)
            if not papers:
                doc.add_paragraph("Aucune.").italic = True
                continue
            for p in papers:
                src = "TCGA" if p.get("source") == "tcga_case" else "PMID"
                line = doc.add_paragraph(style="List Bullet")
                line.add_run(f"{src} {p.get('pmid','')} — ").bold = True
                line.add_run(p.get("title", ""))
                if p.get("relevance"):
                    line.add_run(f"\n{p['relevance']}").italic = True
                if p.get("url"):
                    line.add_run(f"\n{p['url']}")

    p = doc.add_paragraph()
    r = p.add_run("Rapport généré automatiquement par PathMind. Diagnostic à valider par un anatomopathologiste habilité.")
    r.italic = True
    r.font.color.rgb = RGBColor(0x80, 0x78, 0x66)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
