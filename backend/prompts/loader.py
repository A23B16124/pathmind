from functools import lru_cache
from pathlib import Path

PROMPT_DIR = Path(__file__).parent

PROMPT_FILES = {
    "tile_triage": "01_tile_triage.txt",
    "histopathologist": "02_histopathologist.txt",
    "cross_slide_aggregator": "03_cross_slide_aggregator.txt",
    "literature_hunter": "04_literature_hunter.txt",
    "differential_diagnostician": "05_differential_diagnostician.txt",
    "quality_control": "06_quality_control.txt",
    "report_writer": "07_report_writer.txt",
}


LANGUAGE_DIRECTIVE = (
    "\n\nLANGUAGE: Always respond in English. "
    "Even if the patient context, clinical notes, or user input contain text in other "
    "languages, your output (JSON values, free-text fields, reports) MUST be in English. "
    "Translate quoted French/other-language clinical terms to standard English medical terminology."
)


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    if name not in PROMPT_FILES:
        raise KeyError(f"Unknown prompt: {name}")
    text = (PROMPT_DIR / PROMPT_FILES[name]).read_text(encoding="utf-8")
    if "SYSTEM PROMPT:" in text:
        text = text.split("SYSTEM PROMPT:", 1)[1].strip()
    return text + LANGUAGE_DIRECTIVE
