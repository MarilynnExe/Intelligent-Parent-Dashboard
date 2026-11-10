from datetime import date, datetime
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

NonBlankStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class UserCreate(BaseModel):
    full_name: NonBlankStr = Field(max_length=150)
    email_or_username: NonBlankStr = Field(max_length=150)
    password: str = Field(min_length=8)
    role: str
    phone_number: Optional[str] = Field(default=None, max_length=30)


    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, value):
        if value is not None and len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 UTF-8 bytes.")
        return value


class UserOut(BaseModel):
    is_active: bool = True
    user_id: int
    full_name: str
    email_or_username: str
    role: str
    phone_number: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class StudentCreate(BaseModel):
    admission_number: NonBlankStr = Field(max_length=50)
    first_name: NonBlankStr = Field(max_length=100)
    last_name: NonBlankStr = Field(max_length=100)
    date_of_birth: date
    gender: Optional[str] = Field(default=None, max_length=20)
    grade_level: NonBlankStr = Field(max_length=50)
    stream: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]] = None


class StudentOut(BaseModel):
    is_archived: bool = False
    student_id: int
    admission_number: str
    first_name: str
    last_name: str
    date_of_birth: date
    gender: Optional[str] = None
    grade_level: str
    stream: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TeacherAssignmentCreate(BaseModel):
    teacher_user_id: int
    grade_level: NonBlankStr = Field(max_length=50)
    stream: NonBlankStr = Field(max_length=50)
    subject_name: NonBlankStr = Field(max_length=100)


class TeacherAssignmentDetailOut(BaseModel):
    assignment_id: int
    teacher_user_id: int
    teacher_name: str
    grade_level: str
    stream: str
    subject_name: str

    model_config = ConfigDict(from_attributes=True)


class ParentLinkCreate(BaseModel):
    parent_user_id: int
    student_id: int
    relationship_type: Optional[str] = Field(default=None, max_length=30)


class ParentLinkDetailOut(BaseModel):
    id: int
    parent_user_id: int
    parent_name: str
    student_id: int
    student_name: str
    admission_number: str
    relationship_type: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AdminStatsOut(BaseModel):
    total_users: int
    total_admins: int
    total_teachers: int
    total_parents: int
    total_students: int
    total_assessments: int
    total_attendance_records: int

class UserUpdate(UserCreate):
    password: Optional[str] = Field(default=None, min_length=8)

class ActiveUpdate(BaseModel):
    is_active: bool

class ArchiveUpdate(BaseModel):
    is_archived: bool
