from pydantic import BaseModel, Field
from typing import Optional


class TileTriageInput(BaseModel):
    slide_path: str
    slide_index: int


class TileTriageOutput(BaseModel):
    slide_index: int
    regions_of_interest: list[dict] = Field(default_factory=list)
    tile_count: int = 0
    confidence: float = 0.0
    summary: str = ""


class HistopathologistInput(BaseModel):
    slide_index: int
    slide_path: str
    regions_of_interest: list[dict] = Field(default_factory=list)


class HistopathologistOutput(BaseModel):
    slide_index: int
    agent_id: str = "histo_a"          # "histo_a" | "histo_b"
    model_used: str = "qwen72b"        # "qwen72b" | "meditron70b"
    findings: str = ""
    grade: Optional[str] = None
    mitotic_index: Optional[str] = None
    margin_status: Optional[str] = None
    confidence: float = 0.0
    raw_json: str = ""                 # full JSON string from LLM


class CrossSlideInput(BaseModel):
    slides_a: list[HistopathologistOutput]   # Histo-A results
    slides_b: list[HistopathologistOutput]   # Histo-B results
    patient_id: str


class CrossSlideOutput(BaseModel):
    synthesis_a: str = ""
    synthesis_b: str = ""
    dominant_pattern: str = ""
    affected_slides: list[int] = Field(default_factory=list)
    disagreements: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class LiteratureHunterInput(BaseModel):
    hypothesis: str
    keywords: list[str] = Field(default_factory=list)


class LiteratureHunterOutput(BaseModel):
    papers: list[dict] = Field(default_factory=list)
    similar_cases: int = 0
    key_findings: str = ""
    confidence: float = 0.0


class DebateRound(BaseModel):
    agent_id: str          # "histo_a" | "histo_b"
    argument: str
    conceded: bool = False


class ChiefInput(BaseModel):
    patient_id: str
    cross_slide: CrossSlideOutput
    literature: LiteratureHunterOutput
    clinical_data: dict = Field(default_factory=dict)


class ChiefOutput(BaseModel):
    debate_rounds: list[DebateRound] = Field(default_factory=list)
    debate_summary: str = ""
    diagnosis: str = ""
    cap_report: dict = Field(default_factory=dict)
    biomarkers: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    report_html: str = ""
