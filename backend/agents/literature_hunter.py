"""
Literature Hunter agent.

Performs semantic RAG over PubMed + TCGA, then asks the LLM to:
 1. Cite which retrieved papers it actually USED to ground the synthesis
    (with PMID/case_id pulled directly from the retrieved hits — no fabrication).
 2. Flag SUGGESTED papers — retrieved hits that look relevant for the
    clinician to consult but that the LLM did not weave into its synthesis.

Returns LiteratureHunterOutput with used_papers + suggested_papers separated.
"""

from __future__ import annotations

import json

from backend.agents.base import BaseAgent
from backend.schemas.agents import (
    LiteratureHunterInput,
    LiteratureHunterOutput,
    LiteraturePaper,
)
from backend.llm import chat
from backend.prompts import load_prompt
from backend.rag import search_literature
from backend.rag.search import format_for_prompt
from backend.utils.json_repair import repair_llm_json


PUBMED_URL = "https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
TCGA_URL = "https://portal.gdc.cancer.gov/cases/{case_id}"


def _hit_to_paper(hit: dict) -> LiteraturePaper:
    """Build a LiteraturePaper from a Qdrant hit (no LLM annotations yet)."""
    pmid = str(hit.get("pmid") or "")
    source = hit.get("source") or "pubmed"
    meta = hit.get("metadata") or {}
    case_id = meta.get("case_id", "")

    if source == "tcga_case":
        ref = case_id or pmid
        url = TCGA_URL.format(case_id=ref) if ref else ""
    else:
        url = PUBMED_URL.format(pmid=pmid) if pmid else ""

    snippet = (hit.get("text") or "")[:320]
    return LiteraturePaper(
        title=hit.get("title", "") or "Untitled",
        pmid=pmid or case_id or "",
        source=source,
        url=url,
        score=float(hit.get("score") or 0.0),
        snippet=snippet,
        journal=meta.get("journal", ""),
        year=str(meta.get("year", "")),
        authors=meta.get("authors", ""),
        relevance="",
    )


class LiteratureHunterAgent(BaseAgent):
    name = "literature_hunter"

    async def run(self, case_id: str, input_data: LiteratureHunterInput) -> LiteratureHunterOutput:
        await self.emit(case_id, "running", f"Literature search: {input_data.hypothesis[:80]}")

        query = " ".join([input_data.hypothesis, *input_data.keywords])[:500]
        pubmed_hits = search_literature(query, limit=8, source_filter="pubmed")
        tcga_hits = search_literature(query, limit=4, source_filter="tcga_case")

        await self.emit(
            case_id, "running",
            f"Retrieved {len(pubmed_hits)} PubMed + {len(tcga_hits)} TCGA",
        )

        all_hits = pubmed_hits + tcga_hits
        # Build a lookup so we can resolve LLM citations back to real metadata.
        by_ref: dict[str, dict] = {}
        for h in all_hits:
            ref = str(h.get("pmid") or h.get("metadata", {}).get("case_id", ""))
            if ref:
                by_ref[ref] = h

        context = (
            f"=== PUBMED HITS ({len(pubmed_hits)}) ===\n{format_for_prompt(pubmed_hits)}\n\n"
            f"=== TCGA SIMILAR CASES ({len(tcga_hits)}) ===\n{format_for_prompt(tcga_hits)}"
        )

        user = (
            f"Working hypothesis: {input_data.hypothesis}\n"
            f"Keywords: {', '.join(input_data.keywords)}\n\n"
            f"Retrieved literature (semantic search over indexed PubMed abstracts + TCGA seed cases):\n\n"
            f"{context}\n\n"
            "Task — output JSON only with this exact schema:\n"
            "{\n"
            '  "key_findings": "<3-5 sentence synthesis grounding the diagnosis>",\n'
            '  "used_refs":      [{"ref": "<PMID or TCGA case_id from above>", "relevance": "<1 sentence>"}],\n'
            '  "suggested_refs": [{"ref": "<PMID or TCGA case_id from above>", "relevance": "<1 sentence>"}]\n'
            "}\n\n"
            "Rules:\n"
            "- used_refs = papers you actually leaned on for key_findings (cite ALL of them).\n"
            "- suggested_refs = retrieved hits NOT used but worth showing to the pathologist "
            "(alternative differential, recent guideline, related cohort).\n"
            "- Every ref MUST come from the retrieved list above. Do not invent PMIDs.\n"
            "- Each list can be empty if nothing fits."
        )

        result = await chat(
            agent_name=self.name,
            system=load_prompt("literature_hunter"),
            messages=[{"role": "user", "content": user}],
            max_tokens=2500,
        )

        await self.emit(case_id, "done", result)

        data = repair_llm_json(result)
        kf_raw = data.get("key_findings") or result
        key_findings = kf_raw if isinstance(kf_raw, str) else json.dumps(kf_raw, ensure_ascii=False)

        def _resolve(refs: list, fallback: list[dict]) -> list[LiteraturePaper]:
            out: list[LiteraturePaper] = []
            seen: set[str] = set()
            for entry in refs or []:
                if not isinstance(entry, dict):
                    continue
                ref = str(entry.get("ref") or entry.get("pmid") or "")
                if not ref or ref in seen:
                    continue
                hit = by_ref.get(ref)
                if not hit:
                    continue
                paper = _hit_to_paper(hit)
                paper.relevance = entry.get("relevance", "") or ""
                out.append(paper)
                seen.add(ref)
            # If the LLM returned nothing usable, surface top retrievals as a graceful fallback.
            if not out and fallback:
                for h in fallback[:3]:
                    out.append(_hit_to_paper(h))
            return out

        used = _resolve(data.get("used_refs"), pubmed_hits[:3])
        # Suggested = retrieved hits that aren't already in `used`.
        used_refs = {p.pmid for p in used}
        leftover = [h for h in all_hits if str(h.get("pmid") or h.get("metadata", {}).get("case_id", "")) not in used_refs]
        suggested = _resolve(data.get("suggested_refs"), leftover[:4])

        return LiteratureHunterOutput(
            used_papers=used,
            suggested_papers=suggested,
            similar_cases=len(tcga_hits) + len(pubmed_hits),
            key_findings=key_findings,
            confidence=0.82,
        )
