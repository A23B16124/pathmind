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
  diagnostician   (ranked DDx with chain-of-thought)
      |
  quality_control (debate: audits diagnostician, challenges)
      |
  report_writer   (final CAP report synthesis)
      |
   [END]
"""

from __future__ import annotations

import asyncio
import json
import os
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
    DiagnosticianInput,
    DiagnosticianOutput,
    QCInput,
    QCOutput,
    ReportWriterInput,
    ChiefOutput,
)
from backend.agents.tile_triage import TileTriageAgent
from backend.agents.histopathologist_a import HistopathologistAAgent
from backend.agents.histopathologist_b import HistopathologistBAgent
from backend.agents.cross_slide import CrossSlideAgent
from backend.agents.literature_hunter import LiteratureHunterAgent
from backend.agents.diagnostician import DiagnosticianAgent
from backend.agents.quality_control import QualityControlAgent
from backend.agents.chief import ChiefAgent

_NODE_TIMEOUT = float(os.environ.get("NODE_TIMEOUT", "300"))


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
    diagnostician_output: Optional[DiagnosticianOutput]
    qc_output: Optional[QCOutput]
    debate_round: int
    debate_history: list[dict]
    report: Optional[ChiefOutput]
    error: Optional[str]


async def _triage_one(case_id: str, path: str, idx: int) -> TileTriageOutput:
    try:
        return await asyncio.wait_for(
            TileTriageAgent.instance().run(case_id, TileTriageInput(slide_path=path, slide_index=idx)),
            timeout=_NODE_TIMEOUT,
        )
    except (asyncio.TimeoutError, Exception) as exc:
        return TileTriageOutput(
            slide_index=idx,
            slide_path=path,
            parse_failed=True,
            summary=f"triage error: {exc}",
        )


async def node_tile_triage(state: PipelineState) -> dict:
    results = await asyncio.gather(*[
        _triage_one(state["case_id"], p, i)
        for i, p in enumerate(state["slide_paths"])
    ])
    embeds_agg = [
        {"slide": r.slide_index, **r.foundation_embeds}
        for r in results if r.foundation_embeds
    ]
    return {"triage_results": list(results), "foundation_embeds_agg": embeds_agg}


def _format_clinical(clinical_data: dict) -> str:
    if not clinical_data:
        return ""
    # Render structured clinical fields in a stable, readable order.
    # Anything in `context` is appended verbatim as the narrative.
    order = [
        ("age",           "Age"),
        ("sex",           "Sexe"),
        ("site",          "Site anatomique"),
        ("sample_type",   "Type de prelevement"),
        ("prior_history", "Antecedents"),
    ]
    parts: list[str] = []
    for key, label in order:
        val = clinical_data.get(key)
        if val not in (None, "", 0):
            parts.append(f"{label}: {val}")
    if (ctx := clinical_data.get("context")):
        parts.append(str(ctx))
    # Capture any extra free-form keys the caller passed.
    known = {k for k, _ in order} | {"context"}
    for k, v in clinical_data.items():
        if k not in known and v not in (None, "", 0):
            parts.append(f"{k}: {v}")
    return " | ".join(parts)


async def node_histo_parallel(state: PipelineState) -> dict:
    good = [t for t in state["triage_results"] if not t.parse_failed]
    failed = [t for t in state["triage_results"] if t.parse_failed]
    clinical_ctx = _format_clinical(state["clinical_data"])

    histo_inputs = [
        HistopathologistInput(
            slide_index=t.slide_index,
            slide_path=t.slide_path or state["slide_paths"][t.slide_index],
            regions_of_interest=t.regions_of_interest,
            clinical_context=clinical_ctx,
        )
        for t in good
    ]

    def _failed_output(t: TileTriageOutput, agent_id: str) -> HistopathologistOutput:
        return HistopathologistOutput(
            slide_index=t.slide_index,
            agent_id=agent_id,
            findings=f"[skipped — slide parse failed: {t.summary}]",
            confidence=0.0,
        )

    if not histo_inputs:
        fallback_a = [_failed_output(t, "histo_a") for t in failed]
        fallback_b = [_failed_output(t, "histo_b") for t in failed]
        return {"histo_a_results": fallback_a, "histo_b_results": fallback_b}

    results_a, results_b = await asyncio.gather(
        asyncio.gather(*[
            asyncio.wait_for(HistopathologistAAgent.instance().run(state["case_id"], inp), timeout=_NODE_TIMEOUT)
            for inp in histo_inputs
        ]),
        asyncio.gather(*[
            asyncio.wait_for(HistopathologistBAgent.instance().run(state["case_id"], inp), timeout=_NODE_TIMEOUT)
            for inp in histo_inputs
        ]),
    )
    return {
        "histo_a_results": list(results_a) + [_failed_output(t, "histo_a") for t in failed],
        "histo_b_results": list(results_b) + [_failed_output(t, "histo_b") for t in failed],
    }


async def node_cross_slide(state: PipelineState) -> dict:
    cross = await CrossSlideAgent.instance().run(
        state["case_id"],
        CrossSlideInput(
            slides_a=state["histo_a_results"],
            slides_b=state["histo_b_results"],
            patient_id=state["patient_id"],
            clinical_context=_format_clinical(state["clinical_data"]),
        ),
    )
    return {"cross_slide": cross}


async def node_literature(state: PipelineState) -> dict:
    cross = state["cross_slide"]
    hypothesis = cross.dominant_pattern or cross.synthesis_a or "indeterminate pathology"
    lit = await LiteratureHunterAgent.instance().run(
        state["case_id"],
        LiteratureHunterInput(
            hypothesis=hypothesis,
            keywords=[cross.dominant_pattern] if cross.dominant_pattern else [],
            clinical_context=_format_clinical(state["clinical_data"]),
        ),
    )
    return {"literature": lit}


def _evidence_cap(
    histo_a: list[HistopathologistOutput] | None,
    histo_b: list[HistopathologistOutput] | None,
) -> float:
    confs = [r.confidence for r in (histo_a or []) + (histo_b or []) if r is not None]
    if not confs:
        return 0.5
    return max(0.0, min(0.92, sum(confs) / len(confs) + 0.10))


async def node_diagnostician(state: PipelineState) -> dict:
    from backend.ws_manager import manager as _mgr
    cap = _evidence_cap(state.get("histo_a_results"), state.get("histo_b_results"))
    round_n = state.get("debate_round", 0) or 0
    qc_feedback = state.get("qc_output") if round_n > 0 else None

    if round_n > 0 and qc_feedback:
        challenges_str = "; ".join((c.get("issue","")[:80] for c in qc_feedback.challenges[:3])) or qc_feedback.revision_request[:160]
        await _mgr.broadcast(state["case_id"], {
            "agent": "debate-arena", "status": "running",
            "content": f"Round {round_n + 1} — DDx revising in light of QC challenges: {challenges_str}",
            "round": round_n + 1, "side": "ddx",
        })

    ddx = await DiagnosticianAgent.instance().run(
        state["case_id"],
        DiagnosticianInput(
            patient_id=state["patient_id"],
            cross_slide=state["cross_slide"],
            literature=state["literature"],
            clinical_data=state["clinical_data"] or {},
            evidence_cap=cap,
            foundation_embeds=state.get("foundation_embeds_agg") or [],
            qc_feedback=qc_feedback,
            debate_round=round_n,
        ),
    )

    await _mgr.broadcast(state["case_id"], {
        "agent": "debate-arena", "status": "running",
        "content": f"Round {round_n + 1} — DDx position: {ddx.primary_diagnosis} (τ {ddx.confidence:.2f})",
        "round": round_n + 1, "side": "ddx",
    })

    history = list(state.get("debate_history") or [])
    history.append({
        "round": round_n + 1, "agent": "differential-diagnostician",
        "diagnosis": ddx.primary_diagnosis,
        "confidence": ddx.confidence,
        "thinking": (ddx.thinking or "")[:500],
        "argument": f"Primary: {ddx.primary_diagnosis} — {ddx.grade} — {ddx.icd_o_code}",
    })
    return {"diagnostician_output": ddx, "debate_history": history}


async def node_quality_control(state: PipelineState) -> dict:
    from backend.ws_manager import manager as _mgr
    round_n = state.get("debate_round", 0) or 0

    qc = await QualityControlAgent.instance().run(
        state["case_id"],
        QCInput(
            patient_id=state["patient_id"],
            diagnostician_output=state["diagnostician_output"],
            cross_slide=state["cross_slide"],
            literature=state["literature"],
            clinical_data=state["clinical_data"] or {},
        ),
    )

    challenges_str = "; ".join((c.get("issue","")[:80] for c in qc.challenges[:3])) or "no major challenges"
    verdict_emoji = {"accepted": "ACCEPTED", "revision_requested": "REVISION REQUESTED", "escalate": "ESCALATED"}.get(qc.verdict, qc.verdict.upper())
    await _mgr.broadcast(state["case_id"], {
        "agent": "debate-arena", "status": "running",
        "content": f"Round {round_n + 1} — QC verdict: {verdict_emoji}. Challenges: {challenges_str}",
        "round": round_n + 1, "side": "qc", "verdict": qc.verdict,
    })

    history = list(state.get("debate_history") or [])
    history.append({
        "round": round_n + 1, "agent": "quality-control",
        "verdict": qc.verdict,
        "confidence": qc.overall_confidence,
        "challenges": [c.get("issue","") for c in qc.challenges[:3]],
        "argument": f"Verdict: {qc.verdict}. {qc.revision_request[:200] if qc.revision_request else ''}",
        "conceded": qc.verdict == "accepted",
    })

    next_round = round_n + 2
    will_loop = qc.verdict == "revision_requested" and (round_n + 1) < _MAX_DEBATE_ROUNDS
    if will_loop:
        await _mgr.broadcast(state["case_id"], {
            "agent": "debate-arena", "status": "running",
            "content": f"Continuing to round {next_round}/{_MAX_DEBATE_ROUNDS} — DDx must respond to QC challenges",
        })
    else:
        reason = (f"max {_MAX_DEBATE_ROUNDS} rounds reached"
                  if (round_n + 1) >= _MAX_DEBATE_ROUNDS
                  else f"QC verdict final: {qc.verdict}")
        await _mgr.broadcast(state["case_id"], {
            "agent": "debate-arena", "status": "done",
            "content": f"Debate concluded — {reason}",
        })

    return {"qc_output": qc, "debate_history": history, "debate_round": round_n + 1}


async def node_report_writer(state: PipelineState) -> dict:
    cap = _evidence_cap(state.get("histo_a_results"), state.get("histo_b_results"))
    report = await ChiefAgent.instance().run(
        state["case_id"],
        ReportWriterInput(
            patient_id=state["patient_id"],
            diagnostician_output=state["diagnostician_output"],
            qc_output=state["qc_output"],
            cross_slide=state["cross_slide"],
            literature=state["literature"],
            clinical_data=state["clinical_data"] or {},
            evidence_cap=cap,
            histo_a_results=state.get("histo_a_results"),
        ),
    )
    return {"report": report}


_MAX_DEBATE_ROUNDS = 2


def _debate_router(state: PipelineState) -> str:
    qc = state.get("qc_output")
    round_n = state.get("debate_round", 0) or 0
    if qc and qc.verdict == "revision_requested" and round_n < _MAX_DEBATE_ROUNDS:
        return "diagnostician"
    return "report_writer"


def build_graph() -> Any:
    g = StateGraph(PipelineState)

    g.add_node("tile_triage", node_tile_triage)
    g.add_node("histo_parallel", node_histo_parallel)
    g.add_node("cross_slide", node_cross_slide)
    g.add_node("literature", node_literature)
    g.add_node("diagnostician", node_diagnostician)
    g.add_node("quality_control", node_quality_control)
    g.add_node("report_writer", node_report_writer)

    g.set_entry_point("tile_triage")
    g.add_edge("tile_triage", "histo_parallel")
    g.add_edge("histo_parallel", "cross_slide")
    g.add_edge("cross_slide", "literature")
    g.add_edge("literature", "diagnostician")
    g.add_edge("diagnostician", "quality_control")
    g.add_conditional_edges(
        "quality_control",
        _debate_router,
        {"diagnostician": "diagnostician", "report_writer": "report_writer"},
    )
    g.add_edge("report_writer", END)

    return g.compile()


_graph = build_graph()


async def run_pipeline(
    case_id: str,
    patient_id: str,
    slide_paths: list[str],
    clinical_data: dict | None = None,
) -> tuple[ChiefOutput, LiteratureHunterOutput, list[dict]]:
    from backend.utils.hallucination_guard import audit_report

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
        "diagnostician_output": None,
        "qc_output": None,
        "debate_round": 0,
        "debate_history": [],
        "report": None,
        "error": None,
    }
    final_state = await _graph.ainvoke(initial_state)

    warnings = audit_report(
        report=final_state["report"],
        literature=final_state["literature"],
        triage=final_state["triage_results"] or [],
        histo_a=final_state["histo_a_results"] or [],
        histo_b=final_state["histo_b_results"] or [],
    )
    extras = {
        "triage_results": [t.model_dump() for t in (final_state["triage_results"] or [])],
        "debate_history": final_state.get("debate_history") or [],
        "histo_a_results": [r.model_dump() for r in (final_state["histo_a_results"] or [])],
        "histo_b_results": [r.model_dump() for r in (final_state["histo_b_results"] or [])],
        "cross_slide": final_state["cross_slide"].model_dump() if final_state["cross_slide"] else None,
        "clinical_data": clinical_data or {},
        "slide_paths": slide_paths,
    }
    return final_state["report"], final_state["literature"], warnings, extras
