from datetime import date
from typing import List, Literal

from pydantic import BaseModel, Field, model_validator


# Only "Absent" counts toward the risk model, so free-text values would be silently ignored.
AttendanceStatus = Literal["Present", "Absent", "Late", "Excused"]


class AttendanceCreate(BaseModel):
    student_id: int
    record_date: date
    status: AttendanceStatus
    remarks: str | None = Field(default=None, max_length=255)


class AttendanceOut(AttendanceCreate):
    attendance_id: int
    recorded_by_teacher_id: int

    class Config:
        from_attributes = True


class AttendanceEntry(BaseModel):
    student_id: int
    status: AttendanceStatus
    remarks: str | None = Field(default=None, max_length=255)


class BulkAttendanceCreate(BaseModel):
    record_date: date
    entries: List[AttendanceEntry]


    @model_validator(mode="after")
    def unique_students(self):
        student_ids = [entry.student_id for entry in self.entries]
        if len(student_ids) != len(set(student_ids)):
            raise ValueError("Each learner may appear only once in an attendance submission.")
        return self
