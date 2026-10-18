from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class UserCreate(BaseModel):
    full_name: str
    email_or_username: str
    password: str
    role: str
    phone_number: Optional[str] = None


class UserOut(BaseModel):
    user_id: int
    full_name: str
    email_or_username: str
    role: str
    phone_number: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class StudentCreate(BaseModel):
    admission_number: str
    first_name: str
    last_name: str
    date_of_birth: date
    gender: Optional[str] = None
    grade_level: str
    stream: Optional[str] = None


class StudentOut(BaseModel):
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
    grade_level: str
    stream: str
    subject_name: str


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
    relationship_type: Optional[str] = None


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