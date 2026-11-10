"""Private immutable messages and per-participant read cursors (additive tables)."""
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from app.core.database import Base

class Conversation(Base):
    __tablename__ = "message_conversations"
    __table_args__ = (UniqueConstraint("student_id", "parent_user_id", "teacher_user_id", name="uq_message_participants"),)
    conversation_id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.student_id"), nullable=False, index=True)
    parent_user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False, index=True)
    teacher_user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False, index=True)
    parent_read_id = Column(Integer, nullable=False, default=0)
    teacher_read_id = Column(Integer, nullable=False, default=0)
    last_message_id = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

class PrivateMessage(Base):
    __tablename__ = "private_messages"
    __table_args__ = (UniqueConstraint("sender_user_id", "client_message_id", name="uq_message_send_retry"),)
    message_id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("message_conversations.conversation_id"), nullable=False, index=True)
    sender_user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    client_message_id = Column(String(36), nullable=False)
    body = Column(Text, nullable=False)
    sent_at = Column(DateTime, nullable=False, default=datetime.utcnow)
