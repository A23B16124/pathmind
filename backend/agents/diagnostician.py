import json
from backend.agents.base import BaseAgent
from backend.schemas.agents import DiagnosticianInput, DiagnosticianOutput
from backend.llm import chat, LLM_BACKEND
from backend.prompts import load_prompt
from backend.utils.json_repair import repair_llm_json

DDX_SCHEMA = {
    "type": "object",
    "properties": {
        "primary_diagnosis": {
            "type": "object",
            "properties": {
                "diagnosis": {"type": "string"},
                "icd_o_code": {"type": "string"},
                "confidence": {"type": "number"},
                "sbr_grade": {"type": "string"},
                "pt_stage": {"type": "string"},
                "pn_stage": {"type": "string"},
                "margin": {"type": "string"},
                "supporting_evidence": {"type": "array", "items": {"type": "string"}},
                "against_evidence": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["diagnosis", "confidence"],
        },
        "differential": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "rank": {"type": "integer"},
                    "diagnosis": {"type": "string"},
                    "confidence": {"type": "number"},
                    "supporting": {"type": "array", "items": {"type": "string"}},
                    "against": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["rank", "diagnosis", "confidence"],
            },
        },
        "recommended_ihc_panel": {"type": "array", "items": {"type": "string"}},
        "ambiguous_features": {"type": "array", "items": {"type": "string"}},
        "thinking": {"type": "string"},
    },
    "required": ["primary_diagnosis", "differential"],
}


class DiagnosticianAgent(BaseAgent):
    name = "differential-diagnostician"

    async def run(self, case_id: str, input_data: DiagnosticianInput) -> DiagnosticianOutput:
        round_label = f" — round {input_data.debate_round + 1}" if input_data.debate_round > 0 else ""
        await self.emit(case_id, "running", f"Differential-Diagnostician formulating ranked DDx{round_label}")
        if input_data.qc_feedback and input_data.debate_round > 0:
            n_chal = len(input_data.qc_feedback.challenges or [])
            first = (input_data.qc_feedback.challenges[0].get("issue", "")[:90]
                     if input_data.qc_feedback.challenges else
                     input_data.qc_feedback.revision_request[:90])
            await self.emit(case_id, "running",
                f"DDx received {n_chal} QC challenge(s) — must address: {first}")

        ddx_count = len(input_data.cross_slide.disagreements) + 2
        await self.emit(
            case_id, "running",
            f"Evaluating {ddx_count} differential candidates — applying chain-of-thought reasoning"
        )

        # Foundation model embeddings summary
        embed_lines = []
        for e in (input_data.foundation_embeds or []):
            uni2 = e.get("uni2") or {}
            v2 = e.get("virchow2") or {}
            if uni2 or v2:
                embed_lines.append(
                    f"Slide {e.get('slide','?')}: "
                    f"UNI2-h {uni2.get('n',0)}p×{uni2.get('dim',0)}d cos={uni2.get('mean_cos_sim',0):.3f} | "
                    f"Virchow2 {v2.get('n',0)}p×{v2.get('dim',0)}d cos={v2.get('mean_cos_sim',0):.3f}"
                )
        embed_section = "\n".join(embed_lines) if embed_lines else "Not available"

        user = (
            f"Patient ID: {input_data.patient_id}\n"
            f"Clinical data: {json.dumps(input_data.clinical_data)}\n\n"
            f"=== FOUNDATION MODEL EMBEDDINGS (UNI2-h + Virchow2) ===\n{embed_section}\n"
            f"Note: high cos-sim (>0.80) = tile cluster cohesion; low (<0.60) = morphologic heterogeneity.\n\n"
            + (f"=== QC FEEDBACK FROM ROUND {input_data.debate_round} ===\n"
               + (input_data.qc_feedback.revision_request if input_data.qc_feedback else "")
               + "\nChallenges:\n"
               + ("\n".join(f"- [{c.get('severity','')}] {c.get('issue','')}: {c.get('counter_argument','')[:200]}"
                              for c in (input_data.qc_feedback.challenges if input_data.qc_feedback else [])))
               + "\nYou MUST address each challenge above. Update your DDx with reasoning that responds to QC.\n\n"
               if input_data.qc_feedback and input_data.debate_round > 0 else "") +
            f"=== HISTO-A SYNTHESIS ===\n{input_data.cross_slide.synthesis_a}\n\n"
            f"=== HISTO-B SYNTHESIS ===\n{input_data.cross_slide.synthesis_b}\n\n"
            f"=== DISAGREEMENTS ===\n"
            + ("\n".join(f"- {d}" for d in input_data.cross_slide.disagreements) or "None")
            + f"\n\n=== DOMINANT PATTERN ===\n{input_data.cross_slide.dominant_pattern}\n\n"
            f"=== LITERATURE ===\n{input_data.literature.key_findings}\n"
            f"Similar cases: {input_data.literature.similar_cases}\n\n"
            f"Produce ranked DDx JSON. Output JSON only."
        )

        base_system = load_prompt("differential_diagnostician")
        if input_data.qc_feedback and input_data.debate_round > 0:
            prev_dx = "(unknown — first revision)"
            revision_preamble = (
                "REVISION MODE — ROUND " + str(input_data.debate_round + 1) + "\n\n"
                "You are revising your previous Differential Diagnosis in response to Quality-Control challenges. "
                "You MUST do ONE of the following:\n"
                "  (a) DEFEND your previous diagnosis — but cite stronger evidence and explicitly counter EACH challenge\n"
                "  (b) REVISE to a different primary diagnosis or grade — explain WHY the QC challenges convinced you\n\n"
                "It is UNACCEPTABLE to repeat your previous output verbatim. Either strengthen your reasoning OR change your position.\n"
                "If QC says grade is inconsistent — pick a final grade and justify. If QC asks to confirm a feature — either confirm with evidence OR remove it.\n"
                "Add a top-level field `revision_response` to your JSON output:\n"
                "{ \"acknowledged_challenges\": [...], \"defense_or_revision\": \"defended|revised\", \"reasoning\": \"...\" }\n\n"
            )
            system = revision_preamble + base_system
        else:
            system = base_system

        result = await chat(
            agent_name=self.name,
            model_key="qwen72b",
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=3000,
            json_schema=None if (input_data.qc_feedback and input_data.debate_round > 0)
                        else (DDX_SCHEMA if LLM_BACKEND == "vllm" else None),
        )

        data = repair_llm_json(result) or {}
        primary = data.get("primary_diagnosis") or {}
        ddx = data.get("differential") or []

        diagnosis = primary.get("diagnosis") or ""
        confidence = float(primary.get("confidence") or 0.0)
        if input_data.evidence_cap is not None:
            confidence = min(confidence, input_data.evidence_cap)

        top_label = f"{diagnosis} (confidence: {confidence:.0%})"
        await self.emit(case_id, "running", f"Primary: {top_label}")
        if ddx:
            alt = ddx[0]
            await self.emit(case_id, "running",
                f"Differential #2: {alt.get('diagnosis','')} ({float(alt.get('confidence',0)):.0%})")

        ambiguous = data.get("ambiguous_features") or []
        if ambiguous:
            await self.emit(case_id, "running",
                f"Ambiguous features flagged: {'; '.join(ambiguous[:2])}")

        await self.emit(case_id, "done", f"DDx complete — primary: {diagnosis}")

        return DiagnosticianOutput(
            primary_diagnosis=diagnosis,
            icd_o_code=primary.get("icd_o_code") or "",
            pt_stage=primary.get("pt_stage") or "",
            pn_stage=primary.get("pn_stage") or "",
            grade=primary.get("sbr_grade") or "",
            margin_status=primary.get("margin") or "",
            confidence=confidence,
            top_ddx=[{"rank": 1, **primary}] + ddx,
            recommended_ihc_panel=data.get("recommended_ihc_panel") or [],
            ambiguous_features=ambiguous,
            thinking=data.get("thinking") or "",
            raw_json=result,
        )
