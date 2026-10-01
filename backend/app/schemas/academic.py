from datetime import date

from pydantic import BaseModel, Field


class AssessmentCreate(BaseModel):
    student_id: int
    subject_name: str
    academic_year: str
    term: str
    assessment_type: str
    score: float = Field(ge=0)
    max_score: float = Field(gt=0)
    assessment_date: date


class AssessmentOut(AssessmentCreate):
    assessment_id: int
    percentage: float
    recorded_by_teacher_id: int

    class Config:
        from_attributes = True
        