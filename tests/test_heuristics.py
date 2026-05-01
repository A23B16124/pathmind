import numpy as np
import pytest
from src.heuristics.mitosis import count_mitoses
from src.heuristics.roi import score_tile, top_rois, TileScore
from src.heuristics.necrosis import estimate_necrosis_pct

def make_tile(r, g, b):
    arr = np.zeros((256, 256, 3), dtype=np.uint8)
    arr[:] = [r, g, b]
    return arr

def test_count_mitoses_empty_tile():
    result = count_mitoses(make_tile(255, 255, 255))
    assert result["count"] == 0
    assert result["detections"] == []

def test_count_mitoses_returns_dict():
    result = count_mitoses(make_tile(130, 80, 160))
    assert "count" in result and "detections" in result

def test_score_tile_white_low():
    score = score_tile(np.zeros(1280), make_tile(255, 255, 255))
    assert score < 0.3

def test_top_rois_returns_k():
    scores = [TileScore(row=i, col=0, score=float(i)/100, reason="x") for i in range(100)]
    top = top_rois(scores, k=10)
    assert len(top) == 10
    assert top[0].score >= top[-1].score

def test_necrosis_grade_field():
    pale_tiles = [make_tile(200, 190, 195) for _ in range(20)]
    result = estimate_necrosis_pct(pale_tiles)
    assert result["grade"] in ("low", "moderate", "high")
    assert "necrotic_tiles" in result
