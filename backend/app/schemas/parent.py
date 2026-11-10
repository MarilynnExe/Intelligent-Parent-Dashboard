from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ChildSummaryOut(BaseModel):
    student_id: int
    admission_number: str
    first_name: str
    last_name: str
    date_of_birth: date
    gender: Optional[str] = None
    grade_level: str
    stream: Optional[str] = None
    relationship_type: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


from app.schemas.academic import AssessmentOut
from pydantic import Field


class AttendanceMonthOut(BaseModel):
    month: str
    recorded: int
    present: int = 0
    absent: int = 0
    late: int = 0
    excused: int = 0


class LearnerProgressOut(BaseModel):
    student_id: int
    term: str
    academic_year: str
    assessments: list[AssessmentOut] = Field(default_factory=list)
    overall_average: Optional[float] = None
    attendance_totals: dict[str, int]
    attendance_months: list[AttendanceMonthOut] = Field(default_factory=list)
    freshness: str
    freshness_message: Optional[str] = None
    calculated_at: Optional[datetime] = None
