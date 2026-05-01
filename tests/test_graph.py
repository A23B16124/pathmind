import pytest
from unittest.mock import Mock, patch, AsyncMock
from src.graph.graph import route_after_qc


def make_state(**kwargs) -> dict:
    base = {
        "case_id": "TEST_001",
        "slides": [],
        "tile_triage": {},
        "histopath": {},
        "aggregator": {},
        "literature": {},
        "differential": {},
        "qc": {},
        "qc_round": 0,
        "report": {},
    }
    base.update(kwargs)
    return base


def test_route_ok():
    state = make_state(
        qc={"verdict": "ok", "issues": [], "confidence": 0.9, "challenged_fields": []},
        qc_round=0,
    )
    assert route_after_qc(state) == "ok"


def test_route_challenge_round0():
    state = make_state(
        qc={
            "verdict": "challenge",
            "issues": ["grade"],
            "confidence": 0.7,
            "challenged_fields": ["grade"],
        },
        qc_round=0,
    )
    assert route_after_qc(state) == "debate"


def test_route_challenge_round2_stops():
    state = make_state(
        qc={
            "verdict": "challenge",
            "issues": ["still"],
            "confidence": 0.6,
            "challenged_fields": [],
        },
        qc_round=2,
    )
    assert route_after_qc(state) == "ok"


def test_build_graph_compiles():
    # Test graph builds successfully (structure validation)
    from src.graph.graph import build_graph
    import sys

    # Mock openslide at the module level to avoid import errors
    sys.modules["openslide"] = Mock()

    try:
        graph = build_graph()
        assert graph is not None
        # Verify graph structure
        assert hasattr(graph, "invoke")
    finally:
        # Cleanup
        if "openslide" in sys.modules:
            del sys.modules["openslide"]
