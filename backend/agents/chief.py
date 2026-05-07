import json
from datetime import datetime, timezone
from backend.agents.base import BaseAgent
from backend.schemas.agents import ReportWriterInput, ChiefOutput, DebateRound
from backend.llm import chat, LLM_BACKEND
from backend.prompts import load_prompt
from backend.utils.json_repair import repair_llm_json

REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "diagnosis_line": {"type": "string"},
        "synoptic": {
            "type": "object",
            "properties": {
                "histologic_type": {"type": "string"},
                "grade": {"type": "string"},
                "tumor_size_mm": {"type": ["integer", "number", "null"]},
                "lymphovascular_invasion": {"type": "string"},
                "perineural_invasion": {"type": "string"},
                "margins": {"type": "object"},
                "pt": {"type": "string"},
                "pn": {"type": "string"},
            },
        },
        "ihc_recommended": {"type": "array", "items": {"type": "object"}},
        "comment": {"type": "string"},
        "pipeline_confidence": {"type": "number"},
        "uncertainty_flags": {"type": "array", "items": {"type": "string"}},
        "debate_summary": {"type": "string"},
        "primary_diagnosis": {"type": "string"},
        "biomarkers": {"type": "array", "items": {"type": "string"}},
        "recommendations": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
    },
    "required": ["primary_diagnosis", "confidence", "debate_summary"],
}


class ChiefAgent(BaseAgent):
    name = "report-writer"

    async def run(self, case_id: str, input_data: ReportWriterInput) -> ChiefOutput:
        await self.emit(case_id, "running", "Report-Writer synthesizing final CAP report")

        ddx = input_data.diagnostician_output
        qc = input_data.qc_output

        if qc.revision_request:
            await self.emit(case_id, "running",
                f"Incorporating QC revision: {qc.revision_request[:100]}")
        if qc.challenges:
            await self.emit(case_id, "running",
                f"Addressing {len(qc.challenges)} QC challenge(s) in final report")

        user = (
            f"Patient ID: {input_data.patient_id}\n"
            f"Clinical data: {json.dumps(input_data.clinical_data)}\n\n"
            f"=== DIFFERENTIAL-DIAGNOSTICIAN ===\n"
            f"Primary diagnosis: {ddx.primary_diagnosis}\n"
            f"ICD-O: {ddx.icd_o_code} | Grade: {ddx.grade}\n"
            f"Stage: {ddx.pt_stage} {ddx.pn_stage} | Margin: {ddx.margin_status}\n"
            f"Confidence: {ddx.confidence:.2f}\n"
            f"IHC panel: {json.dumps(ddx.recommended_ihc_panel)}\n\n"
            f"=== QUALITY-CONTROL ===\n"
            f"Verdict: {qc.verdict}\n"
            f"QC confidence: {qc.overall_confidence:.2f}\n"
            f"Challenges: {json.dumps([c.get('issue','') for c in qc.challenges])}\n"
            f"Missing workup: {json.dumps(qc.missing_workup)}\n"
            f"Revision request: {qc.revision_request or 'None'}\n\n"
            f"=== LITERATURE ===\n{input_data.literature.key_findings}\n"
            f"Similar cases: {input_data.literature.similar_cases}\n\n"
            f"=== CROSS-SLIDE SYNTHESIS ===\n{input_data.cross_slide.synthesis_a}\n\n"
            f"Generate final CAP report JSON. Incorporate QC feedback. Output JSON only."
        )

        result = await chat(
            agent_name=self.name,
            model_key="claude-cli",
            system=load_prompt("report_writer"),
            messages=[{"role": "user", "content": user}],
            max_tokens=4000,
            json_schema=None,
        )

        await self.emit(case_id, "done", result)

        data = repair_llm_json(result)
        parse_failed = not bool(data)

        if parse_failed:
            await self.emit(case_id, "error", "Report-Writer JSON parse failed — degraded output")

        synoptic = data.get("synoptic") or {} if data else {}
        ihc = data.get("ihc_recommended") or [] if data else []
        biomarkers = [m.get("marker", str(m)) for m in ihc] if ihc else (ddx.recommended_ihc_panel or [])

        # ── COMPOSITE CONFIDENCE ────────────────────────────────────
        # Weighted average across signals — replaces brittle min() chain.
        # Each component bounded to [0, 1]. Final value reflects multi-agent
        # consensus, not the most pessimistic single signal.
        report_conf = 0.0 if parse_failed else float((data or {}).get("confidence") or (data or {}).get("pipeline_confidence") or 0.85)
        ddx_conf = float(ddx.confidence or 0.0)
        qc_conf  = float(qc.overall_confidence or 0.0)
        # Use histo-A mean (image-based, reliable) for proxy — not diluted by text-only histo-B
        histo_a = input_data.histo_a_results or []
        if histo_a:
            histo_proxy = max(0.0, min(0.92, sum(r.confidence for r in histo_a) / len(histo_a)))
        elif input_data.evidence_cap is not None:
            histo_proxy = max(0.0, min(0.92, input_data.evidence_cap - 0.10))
        else:
            histo_proxy = 0.0
        # QC verdict multiplier — revision_requested raised 0.85->0.92 (valid challenges still penalise but less)
        qc_mult = {"accepted": 1.00, "revision_requested": 0.92, "escalate": 0.60}.get(qc.verdict, 0.92)

        composite = (
            0.35 * ddx_conf +
            0.25 * histo_proxy +
            0.20 * qc_conf +
            0.20 * report_conf
        ) * qc_mult
        composite = max(0.0, min(1.0, composite))
        raw_conf = composite

        confidence_breakdown = {
            "ddx_model":       round(ddx_conf, 3),
            "histo_mean":      round(histo_proxy, 3),
            "qc_pipeline":     round(qc_conf, 3),
            "report_writer":   round(report_conf, 3),
            "qc_verdict_mult": round(qc_mult, 2),
            "composite":       round(composite, 3),
            "formula":         "0.35·ddx + 0.25·histo + 0.20·qc + 0.20·report — × qc_verdict_mult",
        }

        primary = (data or {}).get("primary_diagnosis") or ddx.primary_diagnosis or ""
        debate_summary = (data or {}).get("debate_summary") or (
            f"Diagnostician proposed {ddx.primary_diagnosis}. "
            f"QC verdict: {qc.verdict}. "
            + (qc.revision_request or "No revision requested.")
        )

        report_html = ""
        if not parse_failed and data:
            diag_line = data.get("diagnosis_line") or primary
            synoptic_html = "".join(
                f"<tr><td style='font-weight:600;padding-right:16px'>{k.replace('_',' ').title()}</td>"
                f"<td>{json.dumps(v) if isinstance(v, (dict,list)) else v}</td></tr>"
                for k, v in synoptic.items()
            )
            ihc_html = "".join(
                f"<li>{m.get('marker','?')} — {m.get('status','pending')}</li>"
                for m in ihc
            ) or "".join(f"<li>{m} — pending</li>" for m in ddx.recommended_ihc_panel)
            challenges_html = "".join(
                f"<li>[{c.get('severity','').upper()}] {c.get('issue','')}</li>"
                for c in qc.challenges
            ) or "<li>No significant challenges</li>"
            report_html = (
                f"<div class='cap-report'>"
                f"<h2>{diag_line}</h2>"
                f"<h3>Synoptic Report</h3><table>{synoptic_html}</table>"
                f"<h3>IHC Panel (Recommended)</h3><ul>{ihc_html}</ul>"
                f"<h3>QC Debate Summary</h3>"
                f"<p><strong>Verdict:</strong> {qc.verdict} | "
                f"<strong>Challenges:</strong></p><ul>{challenges_html}</ul>"
                f"<p>{debate_summary}</p>"
                f"<h3>Comment</h3><p>{data.get('comment','')}</p>"
                f"<p class='ai-disclosure' style='font-size:11px;color:#666;margin-top:12px'>"
                f"AI-assisted analysis (PathMind v0.2 · AMD MI300X · {datetime.now(timezone.utc).strftime('%Y-%m-%d')}). "
                f"Must be reviewed by a licensed pathologist before clinical use.</p>"
                f"</div>"
            )

        debate_rounds = [
            DebateRound(agent_id="differential-diagnostician", argument=ddx.thinking or f"Proposed: {ddx.primary_diagnosis}"),
        ]
        for ch in qc.challenges:
            debate_rounds.append(DebateRound(
                agent_id="quality-control",
                argument=f"[{ch.get('severity','').upper()}] {ch.get('issue','')}",
                conceded=False,
            ))

        return ChiefOutput(
            debate_rounds=debate_rounds,
            debate_summary=debate_summary,
            diagnosis=primary,
            biomarkers=biomarkers,
            confidence=raw_conf,
            confidence_breakdown=confidence_breakdown,
            cap_report=data or {},
            report_html=report_html,
        )
