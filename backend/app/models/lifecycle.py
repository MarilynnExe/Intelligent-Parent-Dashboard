"""Additive lifecycle and correction-history tables; no legacy columns are altered."""
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from app.core.database import Base

class UserLifecycle(Base):
    __tablename__ = "user_lifecycle"
    user_id = Column(Integer, ForeignKey("users.user_id"), primary_key=True)
    is_active = Column(Boolean, nullable=False, default=True)
    token_version = Column(Integer, nullable=False, default=0)

class StudentLifecycle(Base):
    __tablename__ = "student_lifecycle"
    student_id = Column(Integer, ForeignKey("students.student_id"), primary_key=True)
    is_archived = Column(Boolean, nullable=False, default=False)

class RecordChange(Base):
    __tablename__ = "record_changes"
    change_id = Column(Integer, primary_key=True, autoincrement=True)
    actor_user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(Integer, nullable=False)
    action = Column(String(30), nullable=False)
    before_json = Column(Text, nullable=True)
    after_json = Column(Text, nullable=True)
    changed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
