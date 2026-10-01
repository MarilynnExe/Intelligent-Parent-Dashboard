from datetime import date

from pydantic import BaseModel


class TeacherAssignmentOut(BaseModel):
    assignment_id: int
    grade_level: str
    stream: str
    subject_name: str

    class Config:
        from_attributes = True


class StudentSummaryOut(BaseModel):
    student_id: int
    admission_number: str
    first_name: str
    last_name: str
    date_of_birth: date
    gender: str | None = None
    grade_level: str
    stream: str | None = None

    class Config:
        from_attributes = True
        