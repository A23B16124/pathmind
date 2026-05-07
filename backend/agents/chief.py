import json
import re
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

        # Build condensed per-slide info for per_slide_summary
        histo_a_list = input_data.histo_a_results or []
        histo_b_list = input_data.histo_b_results or []
        per_slide_lines = []
        for i, h in enumerate(histo_a_list):
            per_slide_lines.append(f"  Slide {i} (Histo-A conf={h.confidence:.2f}): {h.findings[:250]}")
        if histo_b_list:
            for i, h in enumerate(histo_b_list[:3]):
                per_slide_lines.append(f"  Slide {i} (Histo-B): {h.findings[:150]}")
        per_slide_section = (
            "=== PER-SLIDE FINDINGS ===\n" + "\n".join(per_slide_lines) + "\n\n"
            if per_slide_lines else ""
        )

        top_ddx_str = json.dumps(ddx.top_ddx[:3]) if ddx.top_ddx else "[]"
        histo_a_conf = round(sum(h.confidence for h in histo_a_list) / len(histo_a_list), 3) if histo_a_list else None
        histo_b_conf = round(sum(h.confidence for h in histo_b_list) / len(histo_b_list), 3) if histo_b_list else None

        user = (
            f"Patient ID: {input_data.patient_id}\n"
            f"Clinical data: {json.dumps(input_data.clinical_data)}\n"
            f"Total slides: {len(histo_a_list)}\n\n"
            f"=== DIFFERENTIAL-DIAGNOSTICIAN ===\n"
            f"Primary diagnosis: {ddx.primary_diagnosis}\n"
            f"ICD-O: {ddx.icd_o_code} | Grade: {ddx.grade}\n"
            f"Stage: {ddx.pt_stage} {ddx.pn_stage} | Margin: {ddx.margin_status}\n"
            f"Thinking: {(ddx.thinking or '')[:400]}\n"
            f"Confidence: {ddx.confidence:.2f}\n"
            f"IHC panel: {json.dumps(ddx.recommended_ihc_panel)}\n"
            f"Top DDx alternatives: {top_ddx_str}\n\n"
            f"=== QUALITY-CONTROL ===\n"
            f"Verdict: {qc.verdict}\n"
            f"QC confidence: {qc.overall_confidence:.2f}\n"
            f"Challenges: {json.dumps([c.get('issue','') for c in qc.challenges])}\n"
            f"Missing workup: {json.dumps(qc.missing_workup)}\n"
            f"Revision request: {qc.revision_request or 'None'}\n\n"
            f"=== READER AGREEMENT ===\n"
            f"Histo-A mean confidence: {histo_a_conf}\n"
            f"Histo-B mean confidence: {histo_b_conf}\n\n"
            f"=== LITERATURE ===\n{input_data.literature.key_findings}\n"
            f"Similar cases: {input_data.literature.similar_cases}\n\n"
            f"=== CROSS-SLIDE SYNTHESIS ===\n{input_data.cross_slide.synthesis_a}\n\n"
            f"{per_slide_section}"
            f"Generate the FULL enriched CAP report JSON with ALL fields from the schema template:\n"
            f"- synoptic: include mitotic_count, necrosis_percent, tumor_budding, stage_group, msi_predicted\n"
            f"- molecular_profiling_recommended: KRAS/NRAS/BRAF/MSI panel with clinical rationale and priority tiers\n"
            f"- differential_diagnosis: top 3 with probability, supporting and against evidence\n"
            f"- treatment_implications: adjuvant_therapy, targeted_therapy, immunotherapy per NCCN\n"
            f"- per_slide_summary: one entry per slide with tumor_present, dominant_pattern, grade, key_findings\n"
            f"- quality_metrics: inter_reader_agreement, histo_a_confidence, histo_b_confidence, qc_debate_rounds, evidence_quality\n"
            f"- ihc_recommended: each marker with rationale field\n"
            f"Output JSON only."
        )

        result = await chat(
            agent_name=self.name,
            model_key="claude-cli",
            system=load_prompt("report_writer"),
            messages=[{"role": "user", "content": user}],
            max_tokens=6000,
            json_schema=None,
        )

        await self.emit(case_id, "done", result)

        data = repair_llm_json(result)
        parse_failed = not bool(data)

        if parse_failed:
            await self.emit(case_id, "error", "Report-Writer JSON parse failed — degraded output")

        if data is None:
            data = {}

        # ── POST-PROCESSING ENRICHMENT ─────────────────────────────
        # Guarantee new fields exist regardless of LLM output completeness.

        # 1. Enrich synoptic with upstream-derived fields
        synoptic = data.get("synoptic") or {}
        if "mitotic_count" not in synoptic:
            # derive from histo_a_list findings (best-effort)
            mitotic_vals = []
            for h in histo_a_list:
                m = re.search(r"(\d+)\s*(?:mitoses?|mitotic)", h.findings or "", re.IGNORECASE)
                if m:
                    mitotic_vals.append(int(m.group(1)))
            if mitotic_vals:
                synoptic["mitotic_count"] = f"{max(mitotic_vals)} per 10 HPF (estimated)"
            else:
                synoptic["mitotic_count"] = "Not reported — insufficient data"
        if "necrosis_percent" not in synoptic:
            synoptic["necrosis_percent"] = None
        if "tumor_budding" not in synoptic:
            synoptic["tumor_budding"] = "Not assessable from available slides"
        if "stage_group" not in synoptic:
            # Derive from pT/pN/pM if possible
            pt = (synoptic.get("pt") or ddx.pt_stage or "").upper()
            pn = (synoptic.get("pn") or ddx.pn_stage or "").upper()
            if "PT4" in pt and "PN1" in pn:
                synoptic["stage_group"] = "Stage IIIC (pT4N1, AJCC 8th ed.)"
            elif "PT3" in pt and "PN0" in pn:
                synoptic["stage_group"] = "Stage IIA (pT3N0, AJCC 8th ed.) — if confirmed"
            elif "PT4" in pt and "PN0" in pn:
                synoptic["stage_group"] = "Stage IIB/IIC (pT4N0, AJCC 8th ed.) — depends on pT4a vs pT4b"
            elif "PN1" in pn or "PN2" in pn:
                synoptic["stage_group"] = "Stage III (pN+) — exact substage requires complete pT/pN"
            else:
                synoptic["stage_group"] = "Cannot be assigned — pN not assessable from submitted slides"
        if "msi_predicted" not in synoptic:
            synoptic["msi_predicted"] = "Not predicted — MMR IHC pending (MLH1/MSH2/MSH6/PMS2 recommended)"
        data["synoptic"] = synoptic

        # 2. Build differential_diagnosis from DDx agent top_ddx
        if not data.get("differential_diagnosis") and ddx.top_ddx:
            ddx_list = []
            for i, alt in enumerate(ddx.top_ddx[:3]):
                ddx_list.append({
                    "rank": i + 1,
                    "diagnosis": alt.get("diagnosis", ""),
                    "probability": alt.get("confidence", 0.0),
                    "key_supporting": alt.get("supporting", []),
                    "key_against": alt.get("against", []),
                })
            data["differential_diagnosis"] = ddx_list

        # 3. Molecular profiling recommendations (colon default; adapt per site)
        if not data.get("molecular_profiling_recommended"):
            diagnosis_str = (ddx.primary_diagnosis or "").lower()
            if any(w in diagnosis_str for w in ["colon", "rectal", "colorectal", "adenocarcinoma"]):
                data["molecular_profiling_recommended"] = [
                    {
                        "test": "Extended RAS panel (KRAS exons 2/3/4, NRAS exons 2/3/4)",
                        "method": "NGS panel or PCR",
                        "clinical_rationale": "Anti-EGFR eligibility (cetuximab/panitumumab): RAS mutation predicts non-response (NCCN CRC v2.2024, PRIME/FIRE-3 trials)",
                        "priority": "Tier 1 — standard of care",
                    },
                    {
                        "test": "BRAF V600E",
                        "method": "PCR or IHC (VE1 clone) + confirmatory NGS",
                        "clinical_rationale": "BRAF V600E mutation: prognostic (poor prognosis), predictive for BRAF/MEK inhibitors (encorafenib + cetuximab, BEACON-CRC)",
                        "priority": "Tier 1 — standard of care",
                    },
                    {
                        "test": "MMR IHC (MLH1, MSH2, MSH6, PMS2) / MSI-PCR",
                        "clinical_rationale": "MSI-H/dMMR: eligibility for pembrolizumab 1L (KEYNOTE-177); Lynch syndrome screening",
                        "method": "IHC panel + reflex PCR if MLH1 loss",
                        "priority": "Tier 1 — standard of care",
                    },
                    {
                        "test": "HER2 amplification",
                        "method": "IHC (score 3+) / FISH confirmation if 2+",
                        "clinical_rationale": "HER2+ CRC (~3%): trastuzumab + pertuzumab or tucatinib combinations (HERACLES-A, MyPathway)",
                        "priority": "Tier 2 — recommended in RAS/BRAF WT",
                    },
                ]

        # 4. Treatment implications
        if not data.get("treatment_implications"):
            stage_group = synoptic.get("stage_group", "")
            data["treatment_implications"] = {
                "stage_context": f"pT={synoptic.get('pt','?')} pN={synoptic.get('pn','?')} — {stage_group}",
                "adjuvant_therapy": (
                    "Stage II high-risk or Stage III: FOLFOX or CAPOX x 6 months per NCCN CRC v2.2024 (de Gramont, MOSAIC trials). "
                    "Final recommendation pending complete staging with lymph node evaluation."
                    if "cannot" not in stage_group.lower() else
                    "Cannot determine — complete staging required (lymph node evaluation pending)"
                ),
                "targeted_therapy": "Anti-EGFR (cetuximab/panitumumab): indicated if RAS/BRAF WT — molecular testing required",
                "immunotherapy": "Pembrolizumab 1L if MSI-H/dMMR confirmed (KEYNOTE-177). MMR IHC panel pending.",
                "clinical_note": "Multidisciplinary tumor board discussion required before initiating treatment. These recommendations are based on morphologic/pathologic findings only.",
            }

        # 5. Per-slide summary from histo_a_list
        if not data.get("per_slide_summary") and histo_a_list:
            slides_summary = []
            for i, h in enumerate(histo_a_list):
                raw_json_str = h.raw_json or ""
                try:
                    hdata = json.loads(raw_json_str) if raw_json_str else {}
                    per_roi = hdata.get("per_roi", [])
                    dom = hdata.get("slide_summary", h.findings[:200])
                    grade_val = (per_roi[0].get("grade") or per_roi[0].get("who_grade") or per_roi[0].get("sbr_grade") or "") if per_roi else h.grade or ""
                    key_f = hdata.get("key_findings", [])
                except Exception:
                    dom = h.findings[:200]
                    grade_val = h.grade or ""
                    key_f = []
                tumor_kw = any(w in (h.findings or "").lower() for w in ["carcinoma", "adenocarcinoma", "tumor", "malignant", "neoplasm"])
                slides_summary.append({
                    "slide_index": i,
                    "tumor_present": tumor_kw,
                    "dominant_pattern": dom[:200] if isinstance(dom, str) else str(dom)[:200],
                    "grade": grade_val,
                    "key_findings": key_f[:3] if key_f else [],
                    "histo_a_confidence": round(h.confidence, 3),
                })
            data["per_slide_summary"] = slides_summary

        # 6. Quality metrics
        if not data.get("quality_metrics"):
            agree = "Not applicable"
            if histo_a_conf is not None and histo_b_conf is not None:
                diff = abs(histo_a_conf - histo_b_conf)
                agree = "High (>0.80)" if diff < 0.15 else ("Moderate (0.60-0.80)" if diff < 0.30 else "Low (<0.60)")
            data["quality_metrics"] = {
                "inter_reader_agreement": agree,
                "histo_a_confidence": histo_a_conf,
                "histo_b_confidence": histo_b_conf,
                "qc_debate_rounds": len(qc.challenges),
                "evidence_quality": (
                    "Strong — multiple high-tissue slides" if len(histo_a_list) >= 5
                    else "Moderate — limited ROIs" if len(histo_a_list) >= 2
                    else "Weak — sparse material"
                ),
            }

        # 7. Add rationale to IHC entries that lack it
        ihc_raw = data.get("ihc_recommended") or []
        _ihc_rationale = {
            "MLH1": "Lynch syndrome screening; MSI-H/dMMR predicts pembrolizumab response",
            "MSH2": "Lynch syndrome screening; MMR panel",
            "MSH6": "Lynch syndrome screening; MMR panel",
            "PMS2": "Lynch syndrome screening; MMR panel",
            "CDX2": "Colon lineage marker; confirms colorectal origin",
            "CK20": "Colorectal differentiation marker; CK20+/CK7- pattern supports colorectal primary",
            "CK7": "Negative in typical CRC; helps exclude upper GI and lung primary",
            "BRAF V600E": "Predictive for BRAF inhibitor eligibility; prognostic in CRC",
        }
        enriched_ihc = []
        for entry in ihc_raw:
            if isinstance(entry, dict):
                marker = entry.get("marker", "")
                if "rationale" not in entry:
                    entry["rationale"] = _ihc_rationale.get(marker, "Standard colorectal adenocarcinoma workup")
                enriched_ihc.append(entry)
            else:
                enriched_ihc.append({"marker": str(entry), "status": "recommended — result pending",
                                      "rationale": _ihc_rationale.get(str(entry), "Standard workup")})
        data["ihc_recommended"] = enriched_ihc

        synoptic = data.get("synoptic") or {}
        ihc = data.get("ihc_recommended") or []
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
