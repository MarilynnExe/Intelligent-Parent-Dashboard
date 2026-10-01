from datetime import date, datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String

from app.core.database import Base


class Student(Base):
    __tablename__ = "students"

    student_id = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    admission_number = Column(
        String(50),
        unique=True,
        nullable=False
    )

    first_name = Column(
        String(100),
        nullable=False
    )

    last_name = Column(
        String(100),
        nullable=False
    )

    date_of_birth = Column(
        Date,
        nullable=False
    )

    gender = Column(
        String(20),
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

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )


class ParentStudent(Base):
    __tablename__ = "parent_student"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    parent_user_id = Column(
        Integer,
        ForeignKey("users.user_id"),
        nullable=False
    )

    student_id = Column(
        Integer,
        ForeignKey("students.student_id"),
        nullable=False
    )

    relationship_type = Column(
        String(30),
        nullable=True
    )


class TeacherAssignment(Base):
    __tablename__ = "teacher_assignments"

    assignment_id = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    teacher_user_id = Column(
        Integer,
        ForeignKey("users.user_id"),
        nullable=False
    )

    grade_level = Column(
        String(50),
        nullable=False
    )

    stream = Column(
        String(50),
        nullable=False
    )

    subject_name = Column(
        String(100),
        nullable=False
    )