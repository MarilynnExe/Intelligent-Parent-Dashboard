from datetime import date, datetime
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from app.core.academic_calendar import term_date_range

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class AssignmentDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Text = Field(max_length=150)
    instructions: str = Field(default="", max_length=4000)
    assigned_date: date
    due_date: date

    @model_validator(mode="after")
    def ordered_dates(self):
        if self.due_date < self.assigned_date:
            raise ValueError("Due date must be on or after the assigned date.")
        return self


class AssignmentCreate(AssignmentDetails):
    grade_level: Text = Field(max_length=50)
    stream: Text = Field(max_length=50)
    subject_name: Text = Field(max_length=100)
    term: Literal["Term 1", "Term 2", "Term 3"]
    academic_year: str = Field(pattern=r"^\d{4}$")

    @model_validator(mode="after")
    def within_period(self):
        start, end = term_date_range(self.term, self.academic_year)
        if not (start <= self.assigned_date <= self.due_date <= end):
            raise ValueError("Assigned and due dates must fall within the selected term/year.")
        return self


class AssignmentOut(AssignmentCreate):
    assignment_id: int
    is_withdrawn: bool
    created_by_teacher_id: int
    created_at: datetime
    notification_delivery: dict | None = None
    model_config = ConfigDict(from_attributes=True)


class AssignmentStatusUpdate(BaseModel):
    is_withdrawn: bool


class CompletionEntry(BaseModel):
    student_id: int
    status: Literal["NOT_SUBMITTED", "SUBMITTED", "EXCUSED"]
    submitted_on: date | None = None
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None = None

    @model_validator(mode="after")
    def submission_date(self):
        if self.status == "SUBMITTED" and self.submitted_on is None:
            raise ValueError("A submitted assignment requires its actual submission date.")
        if self.status != "SUBMITTED" and self.submitted_on is not None:
            raise ValueError("Only submitted work can have a submission date.")
        return self


class CompletionBulkUpdate(BaseModel):
    entries: list[CompletionEntry] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def unique_students(self):
        ids = [entry.student_id for entry in self.entries]
        if len(set(ids)) != len(ids):
            raise ValueError("Each learner must appear only once.")
        return self


class CompletionOut(BaseModel):
    completion_id: int
    student_id: int
    student_name: str
    admission_number: str
    status: str
    display_status: str
    submitted_on: date | None
    reason: str | None
    updated_at: datetime
    editable: bool


class AssignmentRegisterOut(BaseModel):
    assignment: AssignmentOut
    recipients: list[CompletionOut]
    as_of: date


class ParentAssignmentItem(BaseModel):
    assignment: AssignmentOut
    status: str
    display_status: str
    submitted_on: date | None
    reason: str | None


class AssignmentGuidance(BaseModel):
    rule_code: str
    priority: str
    text: str


class AssignmentSummaryOut(BaseModel):
    student_id: int
    term: str
    academic_year: str
    as_of: date
    assignments: list[ParentAssignmentItem]
    counts: dict[str, int]
    due_count: int
    completed_due_count: int
    completion_rate: float | None
    guidance: list[AssignmentGuidance]
