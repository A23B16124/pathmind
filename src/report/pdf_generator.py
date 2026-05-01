from fpdf import FPDF
from src.schemas import ReportOutput

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


class PathMindPDF(FPDF):
    def header(self):
        self.set_font("DejaVu", size=9)
        self.set_text_color(150, 150, 150)
        self.cell(0, 8, "PathMind — Rapport d'anatomopathologie", align="R", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font("DejaVu", size=8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")


def generate_report(report: ReportOutput, out_path: str) -> None:
    pdf = PathMindPDF()
    pdf.add_font("DejaVu", "", FONT_PATH, uni=True)
    pdf.add_font("DejaVu", "B", FONT_BOLD, uni=True)
    pdf.add_page()

    pdf.set_font("DejaVu", "B", 18)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 12, "Compte-rendu Anatomopathologique", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    pdf.set_font("DejaVu", "B", 12)
    pdf.cell(0, 8, f"Cas : {report.case_id}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 12)
    pdf.cell(0, 8, f"Diagnostic final : {report.final_diagnosis}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Grade Nottingham : {report.grade}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("DejaVu", "B", 11)
    pdf.cell(0, 8, "Résumé", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 10)
    pdf.multi_cell(0, 6, report.summary_paragraph)
    pdf.ln(4)

    pdf.set_font("DejaVu", "B", 11)
    pdf.cell(0, 8, "Données histologiques", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 10)
    for k, v in report.structured_findings.items():
        pdf.cell(0, 6, f"  {k} : {v}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    if report.qc_debate_log:
        pdf.set_font("DejaVu", "B", 11)
        pdf.cell(0, 8, "Journal de contrôle qualité", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("DejaVu", "", 9)
        for entry in report.qc_debate_log:
            pdf.multi_cell(0, 5, f"  Round {entry.get('round', '?')} — {entry.get('issue', '')} : {entry.get('resolution', '')}")
        pdf.ln(4)

    if report.references:
        pdf.set_font("DejaVu", "B", 11)
        pdf.cell(0, 8, "Références bibliographiques", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("DejaVu", "", 9)
        for ref in report.references[:10]:
            pdf.multi_cell(0, 5, f"  [{ref.get('pmid', '')}] {ref.get('title', '')} ({ref.get('year', '')})")

    pdf.output(out_path)
