import os
from dotenv import load_dotenv

load_dotenv()

MOCK_MODE = os.getenv("MOCK_MODE", "false").lower() in ("true", "1", "yes")
LLM_BACKEND = os.getenv("LLM_BACKEND", "anthropic").lower()  # "anthropic" or "vllm"
MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-6")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")

MODEL_MAP = {
    "qwen72b":     os.getenv("VLLM_MODEL_QWEN72B",    "Qwen/Qwen2.5-72B-Instruct"),
    "meditron70b": os.getenv("VLLM_MODEL_MEDITRON",   "epfl-llm/meditron-70b"),
    "default":     os.getenv("LLM_MODEL",              "claude-sonnet-4-6"),
}

_anthropic_client = None
_openai_client = None


def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        from anthropic import AsyncAnthropic
        _anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", "dummy"))
    return _anthropic_client


def _get_openai():
    global _openai_client
    if _openai_client is None:
        from openai import AsyncOpenAI
        _openai_client = AsyncOpenAI(
            api_key=os.getenv("VLLM_API_KEY", "EMPTY"),
            base_url=LLM_BASE_URL or "http://localhost:8000/v1",
        )
    return _openai_client


_MOCK_RESPONSES = {
    "tile_triage": '{"slide_id": "slide_0", "quality_ok": true, "quality_issues": [], "rois": [{"roi_id": "roi_001", "priority": 0.94, "x": 12500, "y": 8300, "width": 2048, "height": 2048, "reason": "High cellular density, suspected invasive carcinoma at glandular interface", "tissue_type": "tumor"}, {"roi_id": "roi_002", "priority": 0.81, "x": 14200, "y": 9100, "width": 2048, "height": 2048, "reason": "Desmoplastic stromal reaction with perineural invasion", "tissue_type": "stroma"}, {"roi_id": "roi_003", "priority": 0.42, "x": 4500, "y": 2200, "width": 2048, "height": 2048, "reason": "Normal pancreatic parenchyma reference", "tissue_type": "normal"}], "excluded_regions": [], "thinking": "Triage prioritized regions with abnormal cellular density and architectural distortion."}',
    "histopathologist": '{"slide_id": "slide_0", "roi_id": "roi_001", "tissue_types": ["invasive carcinoma", "desmoplastic stroma", "lymphocytic infiltrate"], "dominant_pattern": "infiltrating ductal carcinoma, no special type", "nuclear_pleomorphism": 3, "nucleoli": "prominent, multiple", "chromatin": "coarse, irregular", "mitotic_count_per_10hpf": 14, "necrosis_percent": 15, "lymphovascular_invasion": "present", "perineural_invasion": "present", "stromal_reaction": "desmoplastic", "sbr_grade": "III", "margin_status": "involved", "confidence": 0.88, "key_findings": ["High-grade nuclear features", "Extensive lymphovascular invasion", "Tumor necrosis ~15%"], "limitations": ["Edge of slide partially out of focus"], "thinking": "Pleomorphism 3, mitoses 14/10HPF, necrosis 15% — SBR grade III."}',
    "histopathologist_a": '{"slide_id": "slide_0", "roi_id": "roi_001", "tissue_types": ["invasive carcinoma", "desmoplastic stroma", "lymphocytic infiltrate"], "dominant_pattern": "infiltrating ductal carcinoma, no special type", "nuclear_pleomorphism": 3, "nucleoli": "prominent, multiple", "chromatin": "coarse, irregular", "mitotic_count_per_10hpf": 14, "necrosis_percent": 15, "lymphovascular_invasion": "present", "perineural_invasion": "present", "stromal_reaction": "desmoplastic", "sbr_grade": "III", "margin_status": "involved", "confidence": 0.88, "key_findings": ["High-grade nuclear features", "Extensive lymphovascular invasion", "Tumor necrosis ~15%"], "limitations": ["Edge of slide partially out of focus"], "thinking": "Pleomorphism 3, mitoses 14/10HPF, necrosis 15% — SBR grade III."}',
    "histopathologist_b": '{"slide_id": "slide_0", "roi_id": "roi_001", "dominant_pattern": "infiltrating ductal carcinoma, acinar variant", "nuclear_pleomorphism": 2, "mitotic_count_per_10hpf": 11, "necrosis_percent": 10, "lymphovascular_invasion": "present", "perineural_invasion": "focal", "sbr_grade": "II", "margin_status": "close (1mm)", "confidence": 0.84, "key_findings": ["Acinar variant pattern", "Lower mitotic count than field A", "Margin close but not involved"], "thinking": "Second read: acinar variant, grade II. Margin assessment differs — 1mm vs involved."}',
    "chief": '{"debate_summary": "Histo-A: grade III, R1 margin. Histo-B: grade II, R0 close margin. Disagreement on margin status and grade. After debate: consensus grade II-III, margin requires step-section. Primary diagnosis confirmed: pancreatic acinar adenocarcinoma.", "primary_diagnosis": "Pancreatic acinar adenocarcinoma, grade II-III (WHO 2022)", "icd_o_code": "8550/3", "pt_stage": "pT2", "pn_stage": "pNx", "margin_status": "R1 anterior 0.5mm (step-section recommended)", "confidence": 0.92, "biomarkers": ["Synaptophysin", "Chromogranin", "IgG4", "Ki-67", "CK7", "CK19"], "similar_cases": 847, "recommendations": ["R0 reresection if feasible", "FOLFIRINOX adjuvant", "MDT discussion mandatory"]}',
    "cross_slide_aggregator": '{"patient_id": "P-DUBOIS-67", "total_slides_analyzed": 12, "slides_with_tumor": [0, 1, 2, 3, 4, 5, 8, 9], "slides_without_tumor": [6, 7, 10, 11], "tumor_map": {"distribution": "multifocal", "estimated_size_mm": 32, "location_description": "head of pancreas, two main foci"}, "consolidated_grade": "II-III", "grade_heterogeneity": true, "dominant_pattern": "infiltrating ductal carcinoma", "margin_status": {"anterior": "involved", "posterior": "clear", "medial": "clear", "lateral": "clear"}, "key_global_features": ["Multifocal tumor distribution", "Variable grade across foci", "Perineural invasion in 3 slides", "Vascular invasion in 2 slides"], "inconsistencies": ["Slide 8 grade II vs adjacent slide 9 grade III"], "suggested_biomarkers": ["CK7", "CK19", "MUC1", "Ki-67"], "confidence": 0.89, "thinking": "Coherent multifocal IDC pattern, anterior margin positive."}',
    "literature_hunter": '{"similar_tcga_cases": [{"case_id": "TCGA-PA-A5YG", "similarity_score": 0.91, "why_similar": "Same multifocal pattern with perineural invasion", "known_diagnosis": "Pancreatic acinar adenocarcinoma grade II", "five_year_os_percent": 28}, {"case_id": "TCGA-IB-7886", "similarity_score": 0.87, "why_similar": "Similar margin involvement and stromal reaction", "known_diagnosis": "PDAC grade II-III", "five_year_os_percent": 22}], "key_papers": [{"pmid": "34521876", "title": "Acinar adenocarcinoma prognosis: 10-year follow-up", "relevance": "Direct match histology + grade", "clinical_implication": "Adjuvant chemo + R0 reresection if feasible"}, {"pmid": "33112045", "title": "Perineural invasion as prognostic marker", "relevance": "Confirms HR 2.3 for local recurrence", "clinical_implication": "Aggressive local control needed"}], "recommended_biomarkers": [{"marker": "Synaptophysin", "rationale": "Exclude neuroendocrine differential"}, {"marker": "IgG4", "rationale": "Exclude autoimmune pancreatitis"}, {"marker": "Ki-67", "rationale": "Proliferation index"}], "population_prognosis": "5-year OS 22-28% for grade II-III pancreatic adenocarcinoma with perineural invasion", "rare_subtype_flag": false, "confidence": 0.85, "thinking": "Match against TCGA pancreas cases. Perineural invasion confirms poor prognosis."}',
    "differential_diagnostician": '{"primary_diagnosis": {"diagnosis": "Pancreatic acinar adenocarcinoma, grade II (WHO 2022)", "icd_o_code": "8550/3", "confidence": 0.91, "sbr_grade": "II", "pt_stage": "pT2", "pn_stage": "pNx", "margin": "R1 anterior 0.5mm", "supporting_evidence": ["Glandular architecture with central necrosis", "14 mitoses/10HPF", "Perineural invasion focal", "Desmoplastic stroma"]}, "differentials": [{"diagnosis": "Neuroendocrine carcinoma G2", "probability": 0.06, "rationale": "Focal trabecular pattern - exclude with synaptophysin/chromogranin IHC", "discriminating_feature": "Synaptophysin negative would exclude"}, {"diagnosis": "IgG4-related sclerosing pancreatitis", "probability": 0.03, "rationale": "Dense stroma but no IgG4+ plasma cells", "discriminating_feature": "IgG4 stain negative"}], "next_steps": ["IHC: synaptophysin, chromogranin, IgG4, Ki-67", "Step-section anterior margin", "MDT discussion"], "confidence": 0.91, "thinking": "Glandular pattern + grade II + perineural invasion = acinar PDAC. NEC excluded if synaptophysin neg."}',
    "quality_control": '{"approved": true, "qc_score": 0.93, "challenges": [{"issue": "R1 margin 0.5mm requires clinical correlation", "severity": "high", "agent_challenged": "histopathologist", "resolution": "Margin status confirmed via review of slides 8-9 step sections"}, {"issue": "Grade heterogeneity II vs III between adjacent slides", "severity": "medium", "agent_challenged": "cross_slide_aggregator", "resolution": "Consolidated grade reported as II-III, dominant grade II"}], "consistency_check": {"all_slides_concordant": false, "discrepancies_resolved": true}, "missing_information": ["Final IHC results", "Imaging correlation"], "diagnostic_confidence_adjustment": -0.02, "final_recommendation": "Approve with caveats. IHC complementary required: synaptophysin, chromogranin, IgG4, Ki-67. Clinical-radiological correlation mandatory."}',
    "report_writer": 'PATHOLOGY REPORT — PathMind AI v0.1\n\nPatient ID: P-DUBOIS-67\nCase ID: dubois-2026-05\nDate: 2026-05-04\nSpecimen: Pancreatic head biopsy, 12 slides\n\nFINAL DIAGNOSIS\nPancreatic acinar adenocarcinoma, grade II (WHO 2022)\nICD-O: 8550/3 | pT2 pNx | R1 anterior margin (0.5mm)\n\nGROSS DESCRIPTION\nMultifocal tumor distribution, head of pancreas. Estimated size 32mm. 8 of 12 slides show tumor involvement.\n\nMICROSCOPIC FINDINGS\n- Architecture: Infiltrating glandular pattern with central necrosis (~15%)\n- Nuclear features: SBR grade III (pleomorphism 3, prominent nucleoli, irregular chromatin)\n- Mitotic activity: 14 mitoses per 10 HPF\n- Stromal reaction: Desmoplastic\n- Lymphovascular invasion: Present (slides 4, 9)\n- Perineural invasion: Present, focal (slides 1, 5, 8)\n- Margins: R1 anterior 0.5mm, posterior/medial/lateral clear\n\nCONSOLIDATED GRADE\nGrade II-III with heterogeneity (dominant grade II, focal grade III in slides 1, 9)\n\nIMMUNOHISTOCHEMISTRY RECOMMENDED\n- Synaptophysin / Chromogranin (exclude neuroendocrine carcinoma)\n- IgG4 (exclude autoimmune pancreatitis)\n- Ki-67 (proliferation index)\n- CK7, CK19, MUC1 (confirm ductal origin)\n\nDIFFERENTIAL DIAGNOSIS\n1. Pancreatic acinar adenocarcinoma grade II (probability 0.91) — primary\n2. Neuroendocrine carcinoma G2 (0.06) — exclude with synaptophysin\n3. IgG4-related sclerosing pancreatitis (0.03) — exclude with IgG4\n\nLITERATURE CONTEXT\n847 similar TCGA cases analyzed. 5-year OS 22-28% for grade II-III pancreatic adenocarcinoma with perineural invasion. Local recurrence HR 2.3 with PNI present (PMID 33112045).\n\nCLINICAL RECOMMENDATIONS\n- R0 reresection if technically feasible (anterior margin)\n- Adjuvant chemotherapy (FOLFIRINOX or gemcitabine-based)\n- MDT discussion mandatory\n- Imaging correlation (MRI pancreas + CT thorax-abdomen-pelvis)\n\nQUALITY CONTROL\nAI confidence: 0.91 | QC score: 0.93\nApproved with caveats: IHC complementary and clinical-radiological correlation required before final treatment decision.',
}


async def chat(
    messages: list[dict],
    system: str = "",
    agent_name: str = "",
    model_key: str = "default",
    max_tokens: int = 2000,
    cache_system: bool = True,
) -> str:
    """Call the LLM. Routes to mock, anthropic (with caching), or vLLM (OpenAI-compat)."""
    if MOCK_MODE:
        if agent_name and agent_name in _MOCK_RESPONSES:
            return _MOCK_RESPONSES[agent_name]
        return _MOCK_RESPONSES["report_writer"]

    if LLM_BACKEND == "anthropic":
        return await _chat_anthropic(messages, system, max_tokens, cache_system)
    return await _chat_openai(messages, system, max_tokens, model_key)


async def _chat_anthropic(messages, system, max_tokens, cache_system):
    client = _get_anthropic()
    sys_param = None
    if system:
        if cache_system:
            sys_param = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        else:
            sys_param = system
    try:
        kwargs = {"model": MODEL, "max_tokens": max_tokens, "messages": messages}
        if sys_param is not None:
            kwargs["system"] = sys_param
        resp = await client.messages.create(**kwargs)
        parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        return "\n".join(parts)
    except Exception as e:
        return f"[LLM error: {e}]"


async def _chat_openai(messages, system, max_tokens, model_key: str = "default"):
    client = _get_openai()
    model_name = MODEL_MAP.get(model_key, MODEL_MAP["default"])
    full = []
    if system:
        full.append({"role": "system", "content": system})
    full.extend(messages)
    try:
        resp = await client.chat.completions.create(
            model=model_name,
            max_tokens=max_tokens,
            messages=full,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        return f"[LLM error: {e}]"
