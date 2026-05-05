"""
PathMind LangGraph pipeline.

Graph topology:
  tile_triage
      |
  histo_parallel  (Qwen72B + Meditron70B concurrently)
      |
  cross_slide     (aggregates dual-read, detects disagreements)
      |
  literature
      |
  chief           (debate + arbitration when disagreements exist)
      |
   [END]
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from langgraph.graph import StateGraph, END
from typing_extensions import TypedDict

from backend.schemas.agents import (
    TileTriageInput,
    TileTriageOutput,
    HistopathologistInput,
    HistopathologistOutput,
    CrossSlideInput,
    CrossSlideOutput,
    LiteratureHunterInput,
    LiteratureHunterOutput,
    ChiefInput,
    ChiefOutput,
)
from backend.agents.tile_triage import TileTriageAgent
from backend.agents.histopathologist_a import HistopathologistAAgent
from backend.agents.histopathologist_b import HistopathologistBAgent
from backend.agents.cross_slide import CrossSlideAgent
from backend.agents.literature_hunter import LiteratureHunterAgent
from backend.agents.chief import ChiefAgent


class PipelineState(TypedDict):
    case_id: str
    patient_id: str
    slide_paths: list[str]
    clinical_data: dict

    triage_results: Optional[list[TileTriageOutput]]
    histo_a_results: Optional[list[HistopathologistOutput]]
    histo_b_results: Optional[list[HistopathologistOutput]]
    cross_slide: Optional[CrossSlideOutput]
    literature: Optional[LiteratureHunterOutput]
    report: Optional[ChiefOutput]
    error: Optional[str]


# ── Node definitions ──────────────────────────────────────────────────────────

async def node_tile_triage(state: PipelineState) -> dict:
    results = await asyncio.gather(*[
        TileTriageAgent().run(
            state["case_id"],
            TileTriageInput(slide_path=p, slide_index=i),
        )
        for i, p in enumerate(state["slide_paths"])
    ])
    return {"triage_results": list(results)}


async def node_histo_parallel(state: PipelineState) -> dict:
    histo_inputs = [
        HistopathologistInput(
            slide_index=t.slide_index,
            slide_path=state["slide_paths"][t.slide_index],
            regions_of_interest=t.regions_of_interest,
        )
        for t in state["triage_results"]
    ]

    results_a, results_b = await asyncio.gather(
        asyncio.gather(*[HistopathologistAAgent().run(state["case_id"], inp) for inp in histo_inputs]),
        asyncio.gather(*[HistopathologistBAgent().run(state["case_id"], inp) for inp in histo_inputs]),
    )
    return {
        "histo_a_results": list(results_a),
        "histo_b_results": list(results_b),
    }


async def node_cross_slide(state: PipelineState) -> dict:
    cross = await CrossSlideAgent().run(
        state["case_id"],
        CrossSlideInput(
            slides_a=state["histo_a_results"],
            slides_b=state["histo_b_results"],
            patient_id=state["patient_id"],
        ),
    )
    return {"cross_slide": cross}


async def node_literature(state: PipelineState) -> dict:
    cross = state["cross_slide"]
    hypothesis = cross.dominant_pattern or cross.synthesis_a or "indeterminate pathology"
    lit = await LiteratureHunterAgent().run(
        state["case_id"],
        LiteratureHunterInput(
            hypothesis=hypothesis,
            keywords=[cross.dominant_pattern] if cross.dominant_pattern else [],
        ),
    )
    return {"literature": lit}


async def node_chief(state: PipelineState) -> dict:
    report = await ChiefAgent().run(
        state["case_id"],
        ChiefInput(
            patient_id=state["patient_id"],
            cross_slide=state["cross_slide"],
            literature=state["literature"],
            clinical_data=state["clinical_data"] or {},
        ),
    )
    return {"report": report}


# ── Graph assembly ────────────────────────────────────────────────────────────

def build_graph() -> Any:
    g = StateGraph(PipelineState)

    g.add_node("tile_triage", node_tile_triage)
    g.add_node("histo_parallel", node_histo_parallel)
    g.add_node("cross_slide", node_cross_slide)
    g.add_node("literature", node_literature)
    g.add_node("chief", node_chief)

    g.set_entry_point("tile_triage")
    g.add_edge("tile_triage", "histo_parallel")
    g.add_edge("histo_parallel", "cross_slide")
    g.add_edge("cross_slide", "literature")
    g.add_edge("literature", "chief")
    g.add_edge("chief", END)

    return g.compile()


# Singleton compiled graph
_graph = build_graph()


async def run_pipeline(
    case_id: str,
    patient_id: str,
    slide_paths: list[str],
    clinical_data: dict | None = None,
) -> ChiefOutput:
    """Invoke the compiled LangGraph pipeline and return the chief report."""
    initial_state: PipelineState = {
        "case_id": case_id,
        "patient_id": patient_id,
        "slide_paths": slide_paths,
        "clinical_data": clinical_data or {},
        "triage_results": None,
        "histo_a_results": None,
        "histo_b_results": None,
        "cross_slide": None,
        "literature": None,
        "report": None,
        "error": None,
    }
    final_state = await _graph.ainvoke(initial_state)
    return final_state["report"]
