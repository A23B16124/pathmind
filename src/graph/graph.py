from langgraph.graph import StateGraph, END
from typing import Literal
from src.schemas import PathMindState


def route_after_qc(state: dict) -> Literal["debate", "ok"]:
    qc = state.get("qc", {})
    verdict = qc.get("verdict", "ok") if isinstance(qc, dict) else qc.verdict
    if verdict == "challenge" and state.get("qc_round", 0) < 2:
        return "debate"
    return "ok"


def build_graph():
    from src.graph.nodes import (
        node_tile_triage,
        node_histopath,
        node_aggregator,
        node_literature,
        node_report,
    )
    from src.graph.debate import node_differential, node_qc

    g = StateGraph(PathMindState)
    for name, fn in [
        ("tile_triage", node_tile_triage),
        ("histopath", node_histopath),
        ("aggregator", node_aggregator),
        ("literature", node_literature),
        ("differential", node_differential),
        ("qc", node_qc),
        ("report", node_report),
    ]:
        g.add_node(name, fn)
    g.set_entry_point("tile_triage")
    g.add_edge("tile_triage", "histopath")
    g.add_edge("histopath", "aggregator")
    g.add_edge("aggregator", "literature")
    g.add_edge("literature", "differential")
    g.add_edge("differential", "qc")
    g.add_conditional_edges(
        "qc", route_after_qc, {"debate": "differential", "ok": "report"}
    )
    g.add_edge("report", END)
    return g.compile()
