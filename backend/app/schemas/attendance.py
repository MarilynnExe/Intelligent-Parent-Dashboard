from datetime import date
from typing import List, Literal

from pydantic import BaseModel


# Only "Absent" counts toward the risk model, so free-text values would be silently ignored.
AttendanceStatus = Literal["Present", "Absent", "Late", "Excused"]


class AttendanceCreate(BaseModel):
    student_id: int
    record_date: date
    status: AttendanceStatus
    remarks: str | None = None


class AttendanceOut(AttendanceCreate):
    attendance_id: int
    recorded_by_teacher_id: int

    class Config:
        from_attributes = True


class AttendanceEntry(BaseModel):
    student_id: int
    status: AttendanceStatus
    remarks: str | None = None


class BulkAttendanceCreate(BaseModel):
    record_date: date
    entries: List[AttendanceEntry]
