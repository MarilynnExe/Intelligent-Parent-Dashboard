from datetime import date, datetime

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, String

from app.core.database import Base


class Assessment(Base):
    __tablename__ = "assessments"

    assessment_id = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    student_id = Column(
        Integer,
        ForeignKey("students.student_id"),
        nullable=False
    )

    subject_name = Column(
        String(100),
        nullable=False
    )

    academic_year = Column(
        String(20),
        nullable=False
    )

    term = Column(
        String(20),
        nullable=False
    )

    assessment_type = Column(
        String(50),
        nullable=False
    )

    score = Column(
        Float,
        nullable=False
    )

    max_score = Column(
        Float,
        nullable=False
    )

    percentage = Column(
        Float,
        nullable=False
    )

    assessment_date = Column(
        Date,
        nullable=False
    )

    recorded_by_teacher_id = Column(
        Integer,
        ForeignKey("users.user_id"),
        nullable=False
    )


class CohortPercentile(Base):
    __tablename__ = "cohort_percentiles"

    percentile_id = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    student_id = Column(
        Integer,
        ForeignKey("students.student_id"),
        nullable=False
    )

    subject_name = Column(
        String(100),
        nullable=True
    )

    grade_level = Column(
        String(50),
        nullable=False
    )

    stream = Column(
        String(50),
        nullable=True
    )

    term = Column(
        String(20),
        nullable=False
    )

    academic_year = Column(
        String(20),
        nullable=False
    )

    percentile_rank = Column(
        Float,
        nullable=False
    )

    calculated_at = Column(
        DateTime,
        default=datetime.utcnow
    )