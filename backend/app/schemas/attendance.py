from datetime import date

from pydantic import BaseModel


class AttendanceCreate(BaseModel):
    student_id: int
    record_date: date
    status: str
    remarks: str | None = None


class AttendanceOut(AttendanceCreate):
    attendance_id: int
    recorded_by_teacher_id: int

    class Config:
        from_attributes = True
        