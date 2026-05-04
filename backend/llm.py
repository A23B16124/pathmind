import os
import random
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

MOCK_MODE = os.getenv("MOCK_MODE", "false").lower() in ("true", "1", "yes")

_client = AsyncOpenAI(
    api_key=os.getenv("ANTHROPIC_API_KEY", "dummy"),
    base_url=os.getenv("LLM_BASE_URL", "https://api.anthropic.com/v1"),
)
MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-6")

_MOCK_RESPONSES = {
    "tile_triage": '{"regions_of_interest": [{"x": 1024, "y": 768, "w": 512, "h": 512, "priority": 0.94}, {"x": 2048, "y": 1536, "w": 256, "h": 256, "priority": 0.81}], "tile_count": 1247, "summary": "Zones tumorales denses identifiées en quadrant supérieur-droit. Infiltration stromale marquée. 2 foyers suspects prioritaires.", "confidence": 0.92}',
    "histopathologist": '{"findings": "Adénocarcinome acineux bien différencié. Glandes tumorales irrégulières avec nécrose centrale. Stroma desmoplastique. Invasion périneurale focale.", "grade": "II", "mitotic_index": "8 mitoses/10 HPF", "margin_status": "R1 - marge antérieure positive 0.5 mm", "confidence": 0.88}',
    "cross_slide": '{"synthesis": "Pattern cohérent sur les 2 lames : adénocarcinome acineux grade II avec composante infiltrante. Extension ganglionnaire non évaluable sur ces lames seules.", "dominant_pattern": "Adénocarcinome acineux grade II", "affected_slides": [0, 1], "confidence": 0.89}',
    "literature_hunter": '{"papers": [{"pmid": "34521876", "title": "Acinar adenocarcinoma prognosis: 10-year follow-up", "journal": "J Pathol", "year": 2023}, {"pmid": "33112045", "title": "Perineural invasion as prognostic marker", "journal": "Mod Pathol", "year": 2022}], "similar_cases": 847, "key_findings": "Survie à 5 ans 72% pour grade II sans métastase. Invasion périneurale associée à récidive locale (HR 2.3). Recommandation marges saines > 1 mm.", "confidence": 0.85}',
    "differential_dx": '{"primary_diagnosis": "Adénocarcinome acineux du pancréas, grade II (OMS 2022)", "differentials": [{"name": "Adénocarcinome acineux", "probability": 0.87, "rationale": "Architecture glandulaire, grade II, invasion périneurale"}, {"name": "Carcinome neuroendocrine G2", "probability": 0.08, "rationale": "Architecture trabéculaire focale, à exclure par IHC synaptophysine"}, {"name": "Pancréatite auto-immune", "probability": 0.05, "rationale": "Stroma dense, mais absence de plasmocytes IgG4"}], "confidence": 0.91}',
    "quality_control": '{"approved": true, "challenges": ["Marge R1 nécessite corrélation clinique", "Invasion périneurale à confirmer sur coupe step-section"], "resolution": "Diagnostic maintenu. Recommande IHC complémentaire : synaptophysine, chromogranine, IgG4 pour écarter DDx. Corrélation avec imagerie préopératoire.", "qc_score": 0.93}',
    "report_writer": "RAPPORT ANATOMOPATHOLOGIQUE CAP — PathMind AI\n\nPatient : P001 | Cas : demo\nDate : 2026-05-04\n\nDIAGNOSTIC PRINCIPAL\nAdénocarcinome acineux du pancréas, grade histologique II (OMS 2022)\n\nFINDINGS\n- Architecture : Glandes tumorales irrégulières, lumières discrètes, nécrose centrale focale\n- Grade : II — différenciation modérée\n- Index mitotique : 8 mitoses / 10 HPF\n- Invasion périneurale : Présente (focale)\n- Marges : R1 — marge antérieure positive (0,5 mm)\n\nBIOMARQUEURS RECOMMANDÉS\n- Synaptophysine / Chromogranine (exclure NEC)\n- IgG4 (exclure pancréatite auto-immune)\n- Ki-67 (index prolifératif)\n\nBASE LITTÉRATURE\n847 cas similaires analysés. Survie à 5 ans 72% (grade II, sans métastase). Invasion périneurale : facteur de risque de récidive locale (HR 2,3).\n\nCONCLUSION\nLésion maligne confirmée. Résection chirurgicale avec marges saines > 1 mm recommandée. Discussion RCP multidisciplinaire indiquée.\n\nConfidence IA : 0.91 | QC score : 0.93",
}

async def chat(messages: list[dict], system: str = "", max_tokens: int = 2000) -> str:
    if MOCK_MODE:
        s = system.lower()
        if "triage" in s:
            return _MOCK_RESPONSES["tile_triage"]
        if "histopathologiste" in s or "histopatholog" in s:
            return _MOCK_RESPONSES["histopathologist"]
        if "agregation" in s or "multi-lames" in s or "cross" in s:
            return _MOCK_RESPONSES["cross_slide"]
        if "bibliograph" in s or "pubmed" in s:
            return _MOCK_RESPONSES["literature_hunter"]
        if "differentiel" in s or "diagnosticien" in s:
            return _MOCK_RESPONSES["differential_dx"]
        if "qc" in s or "qualit" in s or "incoher" in s:
            return _MOCK_RESPONSES["quality_control"]
        if "cap" in s or "rapport" in s or "redacteur" in s:
            return _MOCK_RESPONSES["report_writer"]
        return _MOCK_RESPONSES["report_writer"]

    full_messages = []
    if system:
        full_messages.append({"role": "system", "content": system})
    full_messages.extend(messages)
    try:
        resp = await _client.chat.completions.create(
            model=MODEL,
            max_tokens=max_tokens,
            messages=full_messages,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        return f"[LLM error: {e}]"
