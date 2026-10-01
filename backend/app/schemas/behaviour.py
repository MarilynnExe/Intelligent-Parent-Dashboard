from datetime import date

from pydantic import BaseModel, Field


class BehaviourCreate(BaseModel):
    student_id: int
    record_date: date | None = None
    category: str
    rating: int = Field(ge=1, le=5)
    teacher_note: str | None = None


class BehaviourOut(BehaviourCreate):
    record_id: int
    recorded_by_teacher_id: int

    class Config:
        from_attributes = True


class TeacherObservationCreate(BaseModel):
    student_id: int
    observation_date: date | None = None
    term: str
    academic_year: str
    observation_text: str


class TeacherObservationOut(TeacherObservationCreate):
    observation_id: int
    teacher_id: int

    class Config:
        from_attributes = True
        