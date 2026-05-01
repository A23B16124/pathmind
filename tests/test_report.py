import pytest
from pathlib import Path
from src.report.pdf_generator import generate_report
from src.schemas import ReportOutput


def make_report(**kwargs):
    base = dict(
        case_id="M_DUBOIS_001",
        final_diagnosis="Carcinome canalaire infiltrant",
        grade="III",
        summary_paragraph="Carcinome de grade élevé avec nécrose à 20%.",
        structured_findings={"grade_nottingham": "III", "lvi": True},
        references=[{"pmid": "12345", "title": "IDC prognosis", "year": 2022}],
        qc_debate_log=[{"round": 1, "issue": "slide_07 outlier", "resolution": "Grade III confirmé"}],
    )
    base.update(kwargs)
    return ReportOutput(**base)


def test_generate_report_creates_file(tmp_path):
    out_path = tmp_path / "report.pdf"
    generate_report(make_report(), str(out_path))
    assert out_path.exists()
    assert out_path.stat().st_size > 1000


def test_generate_report_utf8_accents(tmp_path):
    report = make_report(
        case_id="TEST",
        summary_paragraph="Résultats : adénocarcinome, évalué grade élevé — cf. réf. bibliographiques."
    )
    out_path = tmp_path / "report_accents.pdf"
    generate_report(report, str(out_path))
    assert out_path.exists()
