from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional


class _StrictModel(BaseModel):
    # Task 6: strict mode — no extra fields silently accepted
    model_config = ConfigDict(extra="ignore", validate_assignment=True)


class TileTriageInput(_StrictModel):
    slide_path: str
    slide_index: int


class TileTriageOutput(_StrictModel):
    slide_index: int
    slide_path: str = ""
    slide_width: int = 0
    slide_height: int = 0
    mpp_x: Optional[float] = None
    objective_power: Optional[float] = None
    regions_of_interest: list[dict] = Field(default_factory=list)
    tile_count: int = 0
    confidence: float = 0.0
    summary: str = ""
    parse_failed: bool = False
    foundation_embeds: dict = Field(default_factory=dict)


class HistopathologistInput(_StrictModel):
    slide_index: int
    slide_path: str
    regions_of_interest: list[dict] = Field(default_factory=list)
    clinical_context: str = ""


class HistopathologistOutput(_StrictModel):
    slide_index: int
    agent_id: str = "histo_a"          # "histo_a" | "histo_b"
    model_used: str = "qwen72b"        # "qwen72b" | "meditron70b"
    findings: str = ""
    grade: Optional[str] = None
    mitotic_index: Optional[str] = None
    margin_status: Optional[str] = None
    confidence: float = 0.0
    raw_json: str = ""                 # full JSON string from LLM


class CrossSlideInput(_StrictModel):
    slides_a: list[HistopathologistOutput]   # Histo-A results
    slides_b: list[HistopathologistOutput]   # Histo-B results
    patient_id: str
    clinical_context: str = ""


class CrossSlideOutput(_StrictModel):
    synthesis_a: str = ""
    synthesis_b: str = ""
    dominant_pattern: str = ""
    affected_slides: list[int] = Field(default_factory=list)
    disagreements: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class LiteratureHunterInput(_StrictModel):
    hypothesis: str
    keywords: list[str] = Field(default_factory=list)
    clinical_context: str = ""


class LiteraturePaper(_StrictModel):
    """A single literature reference with provenance.

    `used` indicates whether the chief/diagnosis cited this paper.
    `suggested` references are surfaced to the clinician but were not used
    in the LLM's reasoning (related cohort, alternative differential, etc.).
    """
    title: str = ""
    pmid: str = ""               # PubMed ID (or TCGA case_id if from TCGA)
    source: str = "pubmed"       # "pubmed" | "tcga_case"
    url: str = ""                # canonical link (PubMed / TCGA portal)
    score: float = 0.0           # cosine similarity from RAG
    snippet: str = ""            # short excerpt (<= 320 chars)
    journal: str = ""
    year: str = ""
    authors: str = ""            # "Smith J et al."
    relevance: str = ""          # one-line why it matters for THIS case


class LiteratureHunterOutput(_StrictModel):
    used_papers: list[LiteraturePaper] = Field(default_factory=list)
    suggested_papers: list[LiteraturePaper] = Field(default_factory=list)
    similar_cases: int = 0
    key_findings: str = ""
    confidence: float = 0.0
    # Legacy field kept for backward compat with existing agents/tests.
    papers: list[dict] = Field(default_factory=list)


class DebateRound(_StrictModel):
    agent_id: str          # "histo_a" | "histo_b"
    argument: str
    conceded: bool = False


class ChiefInput(_StrictModel):
    patient_id: str
    cross_slide: CrossSlideOutput
    literature: LiteratureHunterOutput
    clinical_data: dict = Field(default_factory=dict)
    # Upper bound on Chief confidence derived from upstream histo-A/B reads.
    # When per-slide readers had thin evidence (e.g. zero patches, text-only
    # blind agent), Chief cannot honestly exceed the average of its sources.
    evidence_cap: Optional[float] = None


class ChiefOutput(_StrictModel):
    confidence_breakdown: dict = Field(default_factory=dict)
    debate_rounds: list[DebateRound] = Field(default_factory=list)
    debate_summary: str = ""
    diagnosis: str = ""
    cap_report: dict = Field(default_factory=dict)
    biomarkers: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    report_html: str = ""


# ── Differential Diagnostician ────────────────────────────────────────────────

class DiagnosticianInput(_StrictModel):
    patient_id: str
    cross_slide: CrossSlideOutput
    literature: LiteratureHunterOutput
    clinical_data: dict = Field(default_factory=dict)
    evidence_cap: Optional[float] = None
    foundation_embeds: list[dict] = Field(default_factory=list)
    qc_feedback: Optional["QCOutput"] = None
    debate_round: int = 0


class DiagnosticianOutput(_StrictModel):
    primary_diagnosis: str = ""
    icd_o_code: str = ""
    pt_stage: str = ""
    pn_stage: str = ""
    grade: str = ""
    margin_status: str = ""
    confidence: float = 0.0
    top_ddx: list[dict] = Field(default_factory=list)
    recommended_ihc_panel: list[str] = Field(default_factory=list)
    ambiguous_features: list[str] = Field(default_factory=list)
    thinking: str = ""
    raw_json: str = ""


# ── Quality Control ───────────────────────────────────────────────────────────

class QCInput(_StrictModel):
    patient_id: str
    diagnostician_output: DiagnosticianOutput
    cross_slide: CrossSlideOutput
    literature: LiteratureHunterOutput
    clinical_data: dict = Field(default_factory=dict)


class QCOutput(_StrictModel):
    verdict: str = "accepted"  # accepted | revision_requested | escalate
    overall_confidence: float = 0.0
    challenges: list[dict] = Field(default_factory=list)
    inconsistencies: list[str] = Field(default_factory=list)
    missing_workup: list[str] = Field(default_factory=list)
    ihc_panel_complete: bool = True
    staging_correct: bool = True
    literature_support_adequate: bool = True
    revision_request: str = ""
    thinking: str = ""
    raw_json: str = ""


# ── Report Writer Input (takes Diagnostician + QC) ────────────────────────────

class ReportWriterInput(_StrictModel):
    patient_id: str
    diagnostician_output: DiagnosticianOutput
    qc_output: QCOutput
    cross_slide: CrossSlideOutput
    literature: LiteratureHunterOutput
    clinical_data: dict = Field(default_factory=dict)
    evidence_cap: Optional[float] = None
    histo_a_results: Optional[list] = None
