from datetime import date

from pydantic import BaseModel, Field, StringConstraints
from typing import Annotated
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class BehaviourCreate(BaseModel):
    student_id: int
    record_date: date | None = None
    category: Text = Field(max_length=50)
    rating: int = Field(ge=1, le=5)
    teacher_note: str | None = Field(default=None, max_length=500)


class BehaviourOut(BehaviourCreate):
    record_id: int
    recorded_by_teacher_id: int

    class Config:
        from_attributes = True


class TeacherObservationCreate(BaseModel):
    student_id: int
    observation_date: date | None = None
    term: Text = Field(max_length=20)
    academic_year: Text = Field(max_length=20)
    observation_text: Text = Field(max_length=1000)


class TeacherObservationOut(TeacherObservationCreate):
    observation_id: int
    teacher_id: int

    class Config:
        from_attributes = True
        