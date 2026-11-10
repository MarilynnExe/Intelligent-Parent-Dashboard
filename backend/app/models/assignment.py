"""Class work and completion records, independent of scored assessments."""
from datetime import datetime
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from app.core.database import Base


class ClassAssignment(Base):
    __tablename__ = "class_assignments"
    assignment_id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(150), nullable=False)
    instructions = Column(Text, nullable=False, default="")
    grade_level = Column(String(50), nullable=False)
    stream = Column(String(50), nullable=False)
    subject_name = Column(String(100), nullable=False)
    term = Column(String(20), nullable=False)
    academic_year = Column(String(20), nullable=False)
    assigned_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)
    is_withdrawn = Column(Boolean, nullable=False, default=False)
    created_by_teacher_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AssignmentCompletion(Base):
    __tablename__ = "assignment_completions"
    __table_args__ = (UniqueConstraint("assignment_id", "student_id", name="uq_assignment_learner"),)
    completion_id = Column(Integer, primary_key=True, autoincrement=True)
    assignment_id = Column(Integer, ForeignKey("class_assignments.assignment_id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("students.student_id"), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="NOT_SUBMITTED")
    submitted_on = Column(Date, nullable=True)
    reason = Column(String(1000), nullable=True)
    recorded_by_teacher_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
