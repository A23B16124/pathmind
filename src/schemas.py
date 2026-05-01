from pydantic import BaseModel, Field
from typing import Literal, Optional, TypedDict


class TileTriageOutput(BaseModel):
    slide_id: str
    total_tiles: int
    tissue_tiles: int
    tissue_pct: float
    top_rois: list[dict]


class HistopathOutput(BaseModel):
    slide_id: str
    grade_nottingham: Literal["I", "II", "III"]
    tubule_formation: int = Field(ge=1, le=3)
    nuclear_pleomorphism: int = Field(ge=1, le=3)
    mitotic_count: int = Field(ge=1, le=3)
    mitoses_per_10hpf: float
    lvi_present: bool
    margin_status: Literal["clear", "close", "involved", "unknown"]
    necrosis_pct: float
    key_findings: list[str]
    confidence: float = Field(ge=0.0, le=1.0)


class AggregatorOutput(BaseModel):
    case_id: str
    consensus_grade: Literal["I", "II", "III"]
    grade_distribution: dict[str, int]
    slide_agreement_pct: float
    outlier_slides: list[str]
    representative_slides: list[str]
    aggregate_lvi: bool
    aggregate_margin: Literal["clear", "close", "involved", "unknown"]
    aggregate_necrosis_pct: float
    summary: str


class LiteratureOutput(BaseModel):
    query_used: str
    references: list[dict]
    key_evidence: list[str]


class DifferentialOutput(BaseModel):
    primary_diagnosis: str
    icd_o_code: str
    grade: Literal["I", "II", "III"]
    staging_notes: str
    differentials: list[dict]
    treatment_implications: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    debate_response: Optional[str] = None


class QCOutput(BaseModel):
    verdict: Literal["ok", "challenge"]
    issues: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    challenged_fields: list[str] = []


class ReportOutput(BaseModel):
    case_id: str
    final_diagnosis: str
    grade: Literal["I", "II", "III"]
    summary_paragraph: str
    structured_findings: dict
    references: list[dict]
    qc_debate_log: list[dict]
    pdf_path: Optional[str] = None


class PathMindState(TypedDict):
    case_id: str
    slides: list[dict]
    tile_triage: dict
    histopath: dict
    aggregator: dict
    literature: dict
    differential: dict
    qc: dict
    qc_round: int
    report: dict
