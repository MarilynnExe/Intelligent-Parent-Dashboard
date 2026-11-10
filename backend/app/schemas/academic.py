from datetime import date

from pydantic import BaseModel, Field, StringConstraints
from typing import Annotated
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class AssessmentCreate(BaseModel):
    student_id: int
    subject_name: Text = Field(max_length=100)
    academic_year: Text = Field(max_length=20)
    term: Text = Field(max_length=20)
    assessment_type: Text = Field(max_length=50)
    score: float = Field(ge=0, allow_inf_nan=False)
    max_score: float = Field(gt=0, allow_inf_nan=False)
    assessment_date: date | None = None


class AssessmentOut(AssessmentCreate):
    analytics_refresh: dict | None = None
    assessment_id: int
    percentage: float
    recorded_by_teacher_id: int

    class Config:
        from_attributes = True
        