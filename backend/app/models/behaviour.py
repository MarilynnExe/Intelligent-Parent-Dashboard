from datetime import date

from sqlalchemy import Column, Date, ForeignKey, Integer, String

from app.core.database import Base


class Attendance(Base):
    __tablename__ = "attendance"

    attendance_id = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    student_id = Column(
        Integer,
        ForeignKey("students.student_id"),
        nullable=False
    )

    record_date = Column(
        Date,
        nullable=False
    )

    status = Column(
        String(20),
        nullable=False
    )

    remarks = Column(
        String(255),
        nullable=True
    )

    recorded_by_teacher_id = Column(
        Integer,
        ForeignKey("users.user_id"),
        nullable=False
    )


class BehaviourRecord(Base):
    __tablename__ = "behaviour_records"

    record_id = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    student_id = Column(
        Integer,
        ForeignKey("students.student_id"),
        nullable=False
    )

    record_date = Column(
        Date,
        nullable=False
    )

    category = Column(
        String(50),
        nullable=False
    )

    rating = Column(
        Integer,
        nullable=False
    )

    teacher_note = Column(
        String(500),
        nullable=True
    )

    recorded_by_teacher_id = Column(
        Integer,
        ForeignKey("users.user_id"),
        nullable=False
    )


class TeacherObservation(Base):
    __tablename__ = "teacher_observations"

    observation_id = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    student_id = Column(
        Integer,
        ForeignKey("students.student_id"),
        nullable=False
    )

    observation_date = Column(
        Date,
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

    observation_text = Column(
        String(1000),
        nullable=False
    )

    teacher_id = Column(
        Integer,
        ForeignKey("users.user_id"),
        nullable=False
    )