from src.llm.client import chat
from src.llm.parser import parse_agent_output
from src.schemas import DifferentialOutput, QCOutput
from src.graph.nodes import load_prompt


async def node_differential(state: dict) -> dict:
    msgs = [
        {
            "role": "system",
            "content": load_prompt("05_differential_diagnostician.txt"),
        },
        {
            "role": "user",
            "content": f"Evidence : {state['aggregator']}\nLittérature : {state['literature']}",
        },
    ]
    qc = state.get("qc", {})
    if isinstance(qc, dict) and qc.get("verdict") == "challenge":
        msgs.append(
            {
                "role": "user",
                "content": f"QC challenge : {qc['issues']}. Argumentez ou révisez.",
            }
        )
    state["differential"] = parse_agent_output(
        await chat(msgs, temperature=0.2), DifferentialOutput
    ).model_dump()
    state["qc_round"] = state.get("qc_round", 0) + 1
    return state


async def node_qc(state: dict) -> dict:
    msgs = [
        {
            "role": "system",
            "content": load_prompt("06_quality_control.txt"),
        },
        {
            "role": "user",
            "content": f"Diagnostic : {state['differential']}\nSlides : {state['histopath']}\nAgrégation : {state['aggregator']}",
        },
    ]
    state["qc"] = parse_agent_output(
        await chat(msgs, temperature=0.0), QCOutput
    ).model_dump()
    return state
