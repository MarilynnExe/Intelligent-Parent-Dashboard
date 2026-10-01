from datetime import date

from pydantic import BaseModel


class UserCreate(BaseModel):
    full_name: str
    email_or_username: str
    password: str
    role: str
    phone_number: str | None = None


class StudentCreate(BaseModel):
    admission_number: str
    first_name: str
    last_name: str
    date_of_birth: date
    gender: str | None = None
    grade_level: str
    stream: str | None = None


class TeacherAssignmentCreate(BaseModel):
    teacher_user_id: int
    grade_level: str
    stream: str
    subject_name: str


class ParentLinkCreate(BaseModel):
    parent_user_id: int
    student_id: int
    relationship_type: str | None = None
    