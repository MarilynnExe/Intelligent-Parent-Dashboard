from datetime import date

from pydantic import BaseModel, Field


class BehaviourCreate(BaseModel):
    student_id: int

    category: str

    rating: int = Field(
        ge=1,
        le=5
    )

    teacher_note: str | None = None

    record_date: date | None = None


class ObservationCreate(BaseModel):
    student_id: int
    term: str
    academic_year: str
    observation_text: str

    