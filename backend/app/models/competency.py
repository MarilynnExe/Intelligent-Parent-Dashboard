"""Teacher-defined competencies and dated evidence; independent of model inputs."""
from datetime import datetime
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text
from app.core.database import Base

class Competency(Base):
    __tablename__ = "competencies"
    competency_id = Column(Integer, primary_key=True, autoincrement=True)
    grade_level = Column(String(50), nullable=False)
    stream = Column(String(50), nullable=False)
    subject_name = Column(String(100), nullable=False)
    strand = Column(String(150), nullable=False, default="")
    name = Column(String(150), nullable=False)
    description = Column(Text, nullable=False, default="")
    is_archived = Column(Boolean, nullable=False, default=False)
    created_by_teacher_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

class CompetencyObservation(Base):
    __tablename__ = "competency_observations"
    observation_id = Column(Integer, primary_key=True, autoincrement=True)
    competency_id = Column(Integer, ForeignKey("competencies.competency_id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("students.student_id"), nullable=False, index=True)
    term = Column(String(20), nullable=False)
    academic_year = Column(String(20), nullable=False)
    observed_on = Column(Date, nullable=False)
    level = Column(String(40), nullable=False)
    evidence = Column(Text, nullable=False)
    recorded_by_teacher_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
