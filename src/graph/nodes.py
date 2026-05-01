from pathlib import Path
from src.llm.client import chat
from src.llm.parser import parse_agent_output
from src.llm.multi_agent import run_agents
from src.schemas import (
    TileTriageOutput,
    HistopathOutput,
    AggregatorOutput,
    LiteratureOutput,
    ReportOutput,
)
from src.wsi.loader import iter_tissue_tiles
from src.wsi.cache import TileCache
from src.heuristics.roi import TileScore, score_tile, top_rois
from src.heuristics.necrosis import estimate_necrosis_pct
import numpy as np


def load_prompt(filename: str) -> str:
    return (Path(__file__).parent.parent.parent / "prompts" / filename).read_text(
        encoding="utf-8"
    )


def format_slide_evidence(slide: dict, triage: dict) -> str:
    return f"Slide ID: {slide['id']}\nPath: {slide.get('path', 'N/A')}\nTriage: {triage}"


async def node_tile_triage(state: dict) -> dict:
    cache = TileCache()
    triage = {}
    for slide in state["slides"]:
        sid = slide["id"]
        key = cache.key(slide["path"], 256, 0)
        tiles = cache.load(key)
        if tiles is None:
            tiles_raw = list(iter_tissue_tiles(slide["path"], tile_size=256, level=0))
            tiles = [t for _, _, t in tiles_raw]
            coords = [(r, c) for r, c, _ in tiles_raw]
            cache.save(key, tiles)
        else:
            coords = [(i // 10, i % 10) for i in range(len(tiles))]
        emb = np.zeros(1280)
        scores = [
            TileScore(row=r, col=c, score=score_tile(emb, t), reason="heuristic")
            for (r, c), t in zip(coords, tiles)
        ]
        rois = top_rois(scores, k=50)
        triage[sid] = TileTriageOutput(
            slide_id=sid,
            total_tiles=len(tiles),
            tissue_tiles=len(tiles),
            tissue_pct=100.0,
            top_rois=[{"row": s.row, "col": s.col, "score": s.score} for s in rois],
        ).model_dump()
    state["tile_triage"] = triage
    return state


async def node_histopath(state: dict) -> dict:
    calls = [
        (
            slide["id"],
            [
                {
                    "role": "system",
                    "content": load_prompt("02_histopathologist.txt"),
                },
                {
                    "role": "user",
                    "content": format_slide_evidence(
                        slide, state["tile_triage"].get(slide["id"], {})
                    ),
                },
            ],
        )
        for slide in state["slides"]
    ]
    raw_outputs = await run_agents(calls)
    state["histopath"] = {
        sid: parse_agent_output(raw, HistopathOutput).model_dump()
        for sid, raw in raw_outputs.items()
    }
    return state


async def node_aggregator(state: dict) -> dict:
    summary = "\n\n".join(
        f"## {sid}\n{data}" for sid, data in state["histopath"].items()
    )
    msgs = [
        {
            "role": "system",
            "content": load_prompt("03_cross_slide_aggregator.txt"),
        },
        {"role": "user", "content": f"Slides :\n{summary}"},
    ]
    state["aggregator"] = parse_agent_output(
        await chat(msgs, temperature=0.1), AggregatorOutput
    ).model_dump()
    return state


async def node_literature(state: dict) -> dict:
    msgs = [
        {
            "role": "system",
            "content": load_prompt("04_literature_hunter.txt"),
        },
        {"role": "user", "content": f"Diagnostic agrégé : {state['aggregator']}"},
    ]
    state["literature"] = parse_agent_output(
        await chat(msgs, temperature=0.1), LiteratureOutput
    ).model_dump()
    return state


async def node_report(state: dict) -> dict:
    msgs = [
        {
            "role": "system",
            "content": load_prompt("07_report_writer.txt"),
        },
        {
            "role": "user",
            "content": (
                f"Diagnostic final : {state['differential']}\n"
                f"QC log : {state.get('qc', {})}\n"
                f"Littérature : {state['literature']}\n"
                f"Agrégation : {state['aggregator']}"
            ),
        },
    ]
    state["report"] = parse_agent_output(
        await chat(msgs, temperature=0.05), ReportOutput
    ).model_dump()
    return state
