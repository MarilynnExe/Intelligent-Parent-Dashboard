from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, Integer, String

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    user_id = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    full_name = Column(
        String(150),
        nullable=False
    )

    email_or_username = Column(
        String(150),
        unique=True,
        nullable=False
    )

    password_hash = Column(
        String(255),
        nullable=False
    )

    role = Column(
        Enum("ADMIN", "TEACHER", "PARENT"),
        nullable=False
    )

    phone_number = Column(
        String(30),
        nullable=True
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )