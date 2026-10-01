from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String

from app.core.database import Base


class StudentAnalytics(Base):
    __tablename__ = "student_analytics"

    analytics_id = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    student_id = Column(
        Integer,
        ForeignKey("students.student_id"),
        nullable=False
    )

    term = Column(
        String(20),
        nullable=False
    )

    academic_year = Column(
        String(20),
        nullable=False
    )

    overall_average = Column(
        Float,
        nullable=True
    )

    support_probability = Column(
        Float,
        nullable=True
    )

    support_status = Column(
        String(50),
        nullable=True
    )

    calculated_at = Column(
        DateTime,
        default=datetime.utcnow
    )


class Recommendation(Base):
    __tablename__ = "recommendations"

    recommendation_id = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    student_id = Column(
        Integer,
        ForeignKey("students.student_id"),
        nullable=False
    )

    term = Column(
        String(20),
        nullable=False
    )

    academic_year = Column(
        String(20),
        nullable=False
    )

    rule_code = Column(
        String(50),
        nullable=False
    )

    recommendation_text = Column(
        String(1000),
        nullable=False
    )

    target_audience = Column(
        String(30),
        nullable=False
    )

    priority = Column(
        String(20),
        nullable=False
    )

    generated_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    status = Column(
        String(20),
        nullable=False,
        default="Active"
    )