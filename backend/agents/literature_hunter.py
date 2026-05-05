from backend.agents.base import BaseAgent
from backend.schemas.agents import LiteratureHunterInput, LiteratureHunterOutput
from backend.llm import chat
from backend.prompts import load_prompt
from backend.rag import search_literature
from backend.rag.search import format_for_prompt


class LiteratureHunterAgent(BaseAgent):
    name = "literature_hunter"

    async def run(self, case_id: str, input_data: LiteratureHunterInput) -> LiteratureHunterOutput:
        await self.emit(case_id, "running", f"Literature search: {input_data.hypothesis[:80]}")

        query = " ".join([input_data.hypothesis, *input_data.keywords])[:500]
        pubmed_hits = search_literature(query, limit=5, source_filter="pubmed")
        tcga_hits = search_literature(query, limit=4, source_filter="tcga_case")

        await self.emit(
            case_id,
            "running",
            f"Retrieved {len(pubmed_hits)} PubMed + {len(tcga_hits)} TCGA",
        )

        context = (
            f"=== PUBMED HITS ({len(pubmed_hits)}) ===\n{format_for_prompt(pubmed_hits)}\n\n"
            f"=== TCGA SIMILAR CASES ({len(tcga_hits)}) ===\n{format_for_prompt(tcga_hits)}"
        )

        user = (
            f"Working hypothesis: {input_data.hypothesis}\n"
            f"Keywords: {', '.join(input_data.keywords)}\n\n"
            f"Retrieved literature (semantic search over indexed PubMed abstracts + TCGA seed cases):\n\n"
            f"{context}\n\n"
            f"Task: synthesize the retrieved literature. Cite real PMIDs and TCGA case IDs from the context above. "
            f"Do not fabricate citations. Output the JSON schema only."
        )

        result = await chat(
            agent_name=self.name,
            system=load_prompt("literature_hunter"),
            messages=[{"role": "user", "content": user}],
            max_tokens=2500,
        )

        await self.emit(case_id, "done", result)
        return LiteratureHunterOutput(
            key_findings=result,
            similar_cases=len(tcga_hits) + len(pubmed_hits),
            confidence=0.82,
        )
