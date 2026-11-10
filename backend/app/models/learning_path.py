"""
Models for Learning Path and Educational Resources Recommender.
"""

from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


class LearningResource(Base):
    __tablename__ = "learning_resources"

    resource_id = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    subject_name = Column(
        String(100),
        nullable=False,
        index=True
    )

    grade_level = Column(
        String(50),
        nullable=False,
        default="Grade 7"
    )

    topic_competency = Column(
        String(200),
        nullable=False
    )

    activity_title = Column(
        String(255),
        nullable=False
    )

    activity_description = Column(
        Text,
        nullable=False
    )

    resource_title = Column(
        String(255),
        nullable=False
    )

    resource_description = Column(
        Text,
        nullable=True
    )

    resource_url = Column(
        String(500),
        nullable=True
    )

    resource_type = Column(
        String(50),
        nullable=False,
        default="Digital Content"
    )

    alignment_type = Column(
        String(50),
        nullable=False,
        default="PROVISIONAL_SUPPORT"
    )  # "CURRICULUM_ALIGNED" vs "PROVISIONAL_SUPPORT"

    alignment_source = Column(
        String(255),
        nullable=True
    )

    is_verified = Column(
        Boolean,
        default=False,
        nullable=False
    )

    suggested_duration = Column(
        String(100),
        nullable=True
    )

    recommended_next_step = Column(
        String(500),
        nullable=True
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )


class LearningPathItem(Base):
    __tablename__ = "learning_path_items"

    path_id = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    student_id = Column(
        Integer,
        ForeignKey("students.student_id"),
        nullable=False,
        index=True
    )

    recommendation_id = Column(
        Integer,
        ForeignKey("recommendations.recommendation_id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    resource_id = Column(
        Integer,
        ForeignKey("learning_resources.resource_id"),
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

    subject_name = Column(
        String(100),
        nullable=False
    )

    topic_competency = Column(
        String(200),
        nullable=False
    )

    reason = Column(
        String(500),
        nullable=False
    )

    activity_title = Column(
        String(255),
        nullable=False
    )

    activity_description = Column(
        Text,
        nullable=False
    )

    resource_title = Column(
        String(255),
        nullable=False
    )

    resource_description = Column(
        Text,
        nullable=True
    )

    resource_url = Column(
        String(500),
        nullable=True
    )

    resource_type = Column(
        String(50),
        nullable=True
    )

    alignment_type = Column(
        String(50),
        nullable=False,
        default="PROVISIONAL_SUPPORT"
    )  # "CURRICULUM_ALIGNED" vs "PROVISIONAL_SUPPORT"

    alignment_source = Column(
        String(255),
        nullable=True
    )

    is_verified = Column(
        Boolean,
        default=False,
        nullable=False
    )

    suggested_duration = Column(
        String(100),
        nullable=True
    )

    recommended_next_step = Column(
        String(500),
        nullable=True
    )

    status = Column(
        String(30),
        nullable=False,
        default="Active"
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
