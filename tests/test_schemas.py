import pytest
from src.schemas import TileTriageOutput, QCOutput

def test_tile_triage_valid():
    t = TileTriageOutput(
        slide_id="slide_01",
        total_tiles=1024,
        tissue_tiles=820,
        tissue_pct=80.1,
        top_rois=[{"row": 0, "col": 0, "score": 0.9, "reason": "high_sat"}]
    )
    assert t.tissue_pct == 80.1

def test_qc_verdict_enum():
    q = QCOutput(verdict="challenge", issues=["Grade incohérent slide_07"], confidence=0.85)
    assert q.verdict == "challenge"

def test_qc_verdict_invalid():
    with pytest.raises(Exception):
        QCOutput(verdict="unknown_value", issues=[], confidence=0.5)
