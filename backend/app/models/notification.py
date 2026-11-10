"""
Notification and Preference Models for Adaptive Communication.
"""

from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String

from app.core.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    notification_id = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    recipient_user_id = Column(
        Integer,
        ForeignKey("users.user_id"),
        nullable=False,
        index=True
    )

    student_id = Column(
        Integer,
        ForeignKey("students.student_id"),
        nullable=True,
        index=True
    )

    category = Column(
        String(50),
        nullable=False
    )  # ACADEMIC, ATTENDANCE, BEHAVIOUR, SUPPORT, SYSTEM

    priority = Column(
        String(20),
        nullable=False,
        default="LOW"
    )  # LOW, MEDIUM, HIGH

    title = Column(
        String(200),
        nullable=False
    )

    message = Column(
        String(1000),
        nullable=False
    )

    suggested_action = Column(
        String(500),
        nullable=True
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    is_read = Column(
        Boolean,
        default=False,
        nullable=False,
        index=True
    )

    read_at = Column(
        DateTime,
        nullable=True
    )

    source_ref = Column(
        String(150),
        nullable=True
    )

    dedup_key = Column(
        String(200),
        nullable=True,
        index=True
    )


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    preference_id = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    user_id = Column(
        Integer,
        ForeignKey("users.user_id"),
        unique=True,
        nullable=False,
        index=True
    )

    notifications_enabled = Column(
        Boolean,
        default=True,
        nullable=False
    )

    academic_updates = Column(
        Boolean,
        default=True,
        nullable=False
    )

    attendance_updates = Column(
        Boolean,
        default=True,
        nullable=False
    )

    behaviour_updates = Column(
        Boolean,
        default=True,
        nullable=False
    )

    support_updates = Column(
        Boolean,
        default=True,
        nullable=False
    )

    communication_style = Column(
        String(20),
        default="DETAILED",
        nullable=False
    )  # DETAILED, CONCISE

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )
