from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class CAPReport(BaseModel):
    patient_id: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    diagnosis: str
    tumor_type: Optional[str] = None
    grade: Optional[str] = None
    margins: Optional[str] = None
    biomarkers: list[str] = Field(default_factory=list)
    similar_cases: int = 0
    confidence: float = 0.0
    differentials: list[dict] = Field(default_factory=list)
    qc_score: float = 0.0
    slide_count: int = 0
