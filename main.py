import asyncio
import argparse
import json
from pathlib import Path
from src.graph.graph import build_graph
from src.observability.stream import emit


async def run_case(case_id: str, slides_dir: str) -> dict:
    slides_path = Path(slides_dir)
    slides = [
        {"id": f.stem, "path": str(f)}
        for f in sorted(list(slides_path.glob("*.svs")) or list(slides_path.glob("*.tiff")))
    ]
    if not slides:
        raise ValueError(f"Aucun slide trouvé dans {slides_dir}")

    state = {
        "case_id": case_id,
        "slides": slides,
        "tile_triage": {},
        "histopath": {},
        "aggregator": {},
        "literature": {},
        "differential": {},
        "qc": {},
        "qc_round": 0,
        "report": {},
    }
    graph = build_graph()
    await emit(case_id, "pipeline_start", {"case_id": case_id, "n_slides": len(slides)})
    final_state = await graph.ainvoke(state)
    await emit(case_id, "report_ready", {"case_id": case_id})
    return final_state["report"]


def main():
    parser = argparse.ArgumentParser(description="PathMind — pipeline WSI vers rapport")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--slides-dir", required=True)
    parser.add_argument("--out", default="report.json")
    args = parser.parse_args()
    result = asyncio.run(run_case(args.case_id, args.slides_dir))
    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Rapport écrit : {args.out}")


if __name__ == "__main__":
    main()
