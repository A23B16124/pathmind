import json
from backend.agents.base import BaseAgent
from backend.schemas.agents import QCInput, QCOutput
from backend.llm import chat, LLM_BACKEND
from backend.prompts import load_prompt
from backend.utils.json_repair import repair_llm_json

QC_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["accepted", "revision_requested", "escalate"]},
        "overall_confidence_in_pipeline": {"type": "number"},
        "challenges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "target_agent": {"type": "string"},
                    "severity": {"type": "string"},
                    "issue": {"type": "string"},
                    "evidence": {"type": "string"},
                    "counter_argument": {"type": "string"},
                },
                "required": ["severity", "issue"],
            },
        },
        "inconsistencies_confirmed": {"type": "array", "items": {"type": "string"}},
        "missing_workup": {"type": "array", "items": {"type": "string"}},
        "ihc_panel_complete": {"type": "boolean"},
        "staging_correct": {"type": "boolean"},
        "literature_support_adequate": {"type": "boolean"},
        "revision_request": {"type": "string"},
        "thinking": {"type": "string"},
    },
    "required": ["verdict", "overall_confidence_in_pipeline"],
}


class QualityControlAgent(BaseAgent):
    name = "quality-control"

    async def run(self, case_id: str, input_data: QCInput) -> QCOutput:
        await self.emit(case_id, "running",
            "Quality-Control auditing Differential-Diagnostician — initiating debate")

        ddx = input_data.diagnostician_output
        await self.emit(case_id, "running",
            f"Reviewing primary diagnosis: {ddx.primary_diagnosis or 'pending'}")

        if ddx.ambiguous_features:
            await self.emit(case_id, "running",
                f"Challenging ambiguous features: {'; '.join(ddx.ambiguous_features[:2])}")

        user = (
            f"Patient ID: {input_data.patient_id}\n"
            f"Clinical data: {json.dumps(input_data.clinical_data)}\n\n"
            f"=== DIFFERENTIAL-DIAGNOSTICIAN OUTPUT ===\n"
            f"Primary: {ddx.primary_diagnosis} (confidence: {ddx.confidence:.2f})\n"
            f"ICD-O: {ddx.icd_o_code}\n"
            f"Grade: {ddx.grade}\n"
            f"Stage: {ddx.pt_stage} {ddx.pn_stage}\n"
            f"Margin: {ddx.margin_status}\n"
            f"Ambiguous features: {json.dumps(ddx.ambiguous_features)}\n"
            f"IHC panel: {json.dumps(ddx.recommended_ihc_panel)}\n"
            f"Full DDx: {json.dumps(ddx.top_ddx)}\n\n"
            f"=== CROSS-SLIDE AGGREGATOR ===\n{input_data.cross_slide.synthesis_a}\n"
            f"Disagreements: {json.dumps(input_data.cross_slide.disagreements)}\n\n"
            f"=== LITERATURE ===\n{input_data.literature.key_findings}\n\n"
            f"Perform critical audit. Challenge any inconsistencies. Output JSON only."
        )

        result = await chat(
            agent_name=self.name,
            model_key="qwen72b",
            system=load_prompt("quality_control"),
            messages=[{"role": "user", "content": user}],
            max_tokens=2500,
            json_schema=QC_SCHEMA if LLM_BACKEND == "vllm" else None,
        )

        data = repair_llm_json(result) or {}
        verdict = data.get("verdict") or "accepted"
        challenges = data.get("challenges") or []
        missing = data.get("missing_workup") or []

        if challenges:
            major = [c for c in challenges if c.get("severity") == "major"]
            minor = [c for c in challenges if c.get("severity") != "major"]
            if major:
                await self.emit(case_id, "running",
                    f"MAJOR challenge: {major[0].get('issue','')[:120]}")
            if minor:
                await self.emit(case_id, "running",
                    f"{len(minor)} minor challenge(s) logged")
        else:
            await self.emit(case_id, "running", "No significant inconsistencies found")

        if missing:
            await self.emit(case_id, "running",
                f"Recommended additional workup: {'; '.join(missing[:2])}")

        verdict_msg = {
            "accepted": "Diagnosis accepted by Quality-Control",
            "revision_requested": f"QC requests revision: {data.get('revision_request','')[:100]}",
            "escalate": "Case escalated — requires senior pathologist review",
        }.get(verdict, verdict)
        await self.emit(case_id, "done", verdict_msg)

        return QCOutput(
            verdict=verdict,
            overall_confidence=float(data.get("overall_confidence_in_pipeline") or 0.0),
            challenges=challenges,
            inconsistencies=data.get("inconsistencies_confirmed") or [],
            missing_workup=missing,
            ihc_panel_complete=bool(data.get("ihc_panel_complete", True)),
            staging_correct=bool(data.get("staging_correct", True)),
            literature_support_adequate=bool(data.get("literature_support_adequate", True)),
            revision_request=data.get("revision_request") or "",
            thinking=data.get("thinking") or "",
            raw_json=result,
        )
