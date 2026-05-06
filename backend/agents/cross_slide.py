"""
Cross-Slide Aggregator.

Aggregates dual-read findings (Histo-A vs Histo-B) across all slides and
identifies disagreements that the Chief will arbitrate.

For >CHUNK_THRESHOLD slides, performs hierarchical map-reduce: chunks of N
slides are aggregated in parallel, then a final pass merges chunk syntheses.
This keeps each LLM call within model context limits and bounds cost growth.
"""

from __future__ import annotations

import asyncio
import json

from backend.agents.base import BaseAgent
from backend.schemas.agents import (
    CrossSlideInput,
    CrossSlideOutput,
    HistopathologistOutput,
)
from backend.llm import chat
from backend.prompts import load_prompt
from backend.utils.json_repair import repair_llm_json


CHUNK_THRESHOLD = 20    # slides above which we chunk
CHUNK_SIZE = 10
FINDINGS_TRUNCATE = 600


def _as_str(v) -> str:
    """Coerce LLM-returned value into a string. Models occasionally emit
    nested objects/lists where a string is expected — flatten via JSON dump.
    """
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    return json.dumps(v, ensure_ascii=False)


def _format_findings(reads: list[HistopathologistOutput]) -> str:
    return "\n".join(
        f"Slide {r.slide_index}: {r.findings[:FINDINGS_TRUNCATE]}" for r in reads
    )


class CrossSlideAgent(BaseAgent):
    name = "cross_slide_aggregator"

    async def run(self, case_id: str, input_data: CrossSlideInput) -> CrossSlideOutput:
        n_slides = len(input_data.slides_a)

        if n_slides <= CHUNK_THRESHOLD:
            await self.emit(
                case_id, "running",
                f"Aggregating {n_slides} slides x2 reads — detecting disagreements",
            )
            return await self._aggregate_single(case_id, input_data, emit_done=True)

        # Hierarchical: chunk both reads in parallel, then reduce.
        n_chunks = (n_slides + CHUNK_SIZE - 1) // CHUNK_SIZE
        await self.emit(
            case_id, "running",
            f"Aggregating {n_slides} slides via map-reduce ({n_chunks} chunks of {CHUNK_SIZE})",
        )

        chunks: list[CrossSlideInput] = []
        for start in range(0, n_slides, CHUNK_SIZE):
            end = min(start + CHUNK_SIZE, n_slides)
            chunks.append(CrossSlideInput(
                slides_a=input_data.slides_a[start:end],
                slides_b=input_data.slides_b[start:end],
                patient_id=input_data.patient_id,
            ))

        partials: list[CrossSlideOutput] = await asyncio.gather(*[
            self._aggregate_single(case_id, chunk, emit_done=False)
            for chunk in chunks
        ])

        # Reduce partials with a final synthesis call.
        reduced = await self._reduce_partials(input_data.patient_id, partials, n_slides)

        await self.emit(
            case_id, "done",
            json.dumps({
                "n_slides": n_slides,
                "n_chunks": n_chunks,
                "disagreements": reduced.disagreements,
                "dominant_pattern": reduced.dominant_pattern,
            }),
        )
        return reduced

    async def _aggregate_single(
        self, case_id: str, inp: CrossSlideInput, *, emit_done: bool,
    ) -> CrossSlideOutput:
        n = len(inp.slides_a)
        clinical_block = (
            f"=== CLINICAL CONTEXT (anchor your synthesis to this) ===\n{inp.clinical_context}\n\n"
            if inp.clinical_context else ""
        )
        user = (
            f"{clinical_block}"
            f"Patient: {inp.patient_id}\n"
            f"Slides analyzed: {n} (each read independently by Histo-A and Histo-B)\n\n"
            f"=== HISTO-A READINGS (Qwen2.5-72B) ===\n{_format_findings(inp.slides_a)}\n\n"
            f"=== HISTO-B READINGS (Meditron-70B) ===\n{_format_findings(inp.slides_b)}\n\n"
            f"Task: (1) Synthesize each reader's cross-slide view (synthesis_a, synthesis_b). "
            f"(2) Identify SPECIFIC disagreements between A and B (grade, margin, LVI, PNI, dominant pattern, biomarker recommendations). "
            f"(3) State the dominant pattern (consensus or A's view if no consensus). "
            f"(4) List affected slide indices. "
            f"Output JSON only with keys: synthesis_a, synthesis_b, dominant_pattern, affected_slides (list of int), disagreements (list of strings)."
        )

        result = await chat(
            agent_name=self.name,
            model_key="qwen72b",
            system=load_prompt("cross_slide_aggregator"),
            messages=[{"role": "user", "content": user}],
            max_tokens=2500,
        )

        if emit_done:
            await self.emit(case_id, "done", result)

        data = repair_llm_json(result)
        return CrossSlideOutput(
            synthesis_a=_as_str(data.get("synthesis_a")) or (result if not data else ""),
            synthesis_b=_as_str(data.get("synthesis_b")),
            dominant_pattern=_as_str(data.get("dominant_pattern")),
            affected_slides=data.get("affected_slides") or [],
            disagreements=[_as_str(d) for d in (data.get("disagreements") or [])],
            confidence=0.89,
        )

    async def _reduce_partials(
        self, patient_id: str, partials: list[CrossSlideOutput], n_slides_total: int,
    ) -> CrossSlideOutput:
        """Final reduction over chunk-level syntheses."""
        bullets = []
        for i, p in enumerate(partials):
            bullets.append(
                f"Chunk {i}: dominant={p.dominant_pattern} | "
                f"slides_affected={p.affected_slides} | "
                f"disagreements={p.disagreements} | "
                f"synth_a={p.synthesis_a[:300]} | "
                f"synth_b={p.synthesis_b[:300]}"
            )

        user = (
            f"Patient: {patient_id} — {n_slides_total} slides processed in {len(partials)} chunks.\n\n"
            f"Chunk-level syntheses:\n" + "\n".join(bullets) + "\n\n"
            f"Task: produce a single case-level synthesis that consolidates all chunks. "
            f"Merge synthesis_a and synthesis_b. Deduplicate disagreements. "
            f"Pick the dominant_pattern that holds across the most chunks (or call out heterogeneity). "
            f"Union all affected_slides. "
            f"Output JSON with keys: synthesis_a, synthesis_b, dominant_pattern, affected_slides, disagreements."
        )

        result = await chat(
            agent_name=self.name,
            model_key="qwen72b",
            system=load_prompt("cross_slide_aggregator"),
            messages=[{"role": "user", "content": user}],
            max_tokens=2500,
        )

        data = repair_llm_json(result)
        all_affected = sorted({s for p in partials for s in p.affected_slides})
        all_disagreements = list(dict.fromkeys(d for p in partials for d in p.disagreements))

        return CrossSlideOutput(
            synthesis_a=_as_str(data.get("synthesis_a")) or "; ".join(p.synthesis_a for p in partials if p.synthesis_a),
            synthesis_b=_as_str(data.get("synthesis_b")) or "; ".join(p.synthesis_b for p in partials if p.synthesis_b),
            dominant_pattern=_as_str(data.get("dominant_pattern")) or (partials[0].dominant_pattern if partials else ""),
            affected_slides=data.get("affected_slides") or all_affected,
            disagreements=[_as_str(d) for d in (data.get("disagreements") or all_disagreements)],
            confidence=0.89,
        )
