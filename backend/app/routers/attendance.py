from datetime import date
from typing import List

from pydantic import BaseModel


class AttendanceEntry(BaseModel):
    student_id: int
    status: str
    remarks: str | None = None


class BulkAttendanceCreate(BaseModel):
    record_date: date
    entries: List[AttendanceEntry]


class AttendanceOut(BaseModel):
    attendance_id: int
    student_id: int
    record_date: date
    status: str
    remarks: str | None = None

    class Config:
        from_attributes = True

        