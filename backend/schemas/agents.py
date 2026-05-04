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
    findings: str = ""
    grade: Optional[str] = None
    mitotic_index: Optional[str] = None
    margin_status: Optional[str] = None
    confidence: float = 0.0

class CrossSlideInput(BaseModel):
    slides: list[HistopathologistOutput]
    patient_id: str

class CrossSlideOutput(BaseModel):
    synthesis: str = ""
    dominant_pattern: str = ""
    affected_slides: list[int] = Field(default_factory=list)
    confidence: float = 0.0

class LiteratureHunterInput(BaseModel):
    hypothesis: str
    keywords: list[str] = Field(default_factory=list)

class LiteratureHunterOutput(BaseModel):
    papers: list[dict] = Field(default_factory=list)
    similar_cases: int = 0
    key_findings: str = ""
    confidence: float = 0.0

class DifferentialDxInput(BaseModel):
    cross_slide: CrossSlideOutput
    literature: LiteratureHunterOutput
    clinical_data: dict = Field(default_factory=dict)

class DifferentialDxOutput(BaseModel):
    differentials: list[dict] = Field(default_factory=list)
    primary_diagnosis: str = ""
    confidence: float = 0.0

class QualityControlInput(BaseModel):
    differential: DifferentialDxOutput
    cross_slide: CrossSlideOutput
    all_slide_findings: list[HistopathologistOutput]

class QualityControlOutput(BaseModel):
    approved: bool = False
    challenges: list[str] = Field(default_factory=list)
    resolution: str = ""
    qc_score: float = 0.0

class ReportWriterInput(BaseModel):
    patient_id: str
    differential: DifferentialDxOutput
    qc: QualityControlOutput
    literature: LiteratureHunterOutput
    cross_slide: CrossSlideOutput

class ReportWriterOutput(BaseModel):
    diagnosis: str = ""
    cap_report: dict = Field(default_factory=dict)
    biomarkers: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    report_html: str = ""
