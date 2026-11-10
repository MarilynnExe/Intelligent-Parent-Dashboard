"""Authorized teacher corrections, record removal and saved attendance registers."""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import require_role
from app.core.academic_calendar import term_date_range, term_for_date
from app.models.user import User
from app.models.student import TeacherAssignment, Student
from app.models.academic import Assessment
from app.models.behaviour import Attendance, BehaviourRecord, TeacherObservation
from app.schemas.academic import AssessmentCreate
from app.schemas.behaviour import BehaviourCreate, TeacherObservationCreate
from app.schemas.attendance import AttendanceOut
from app.routers.teacher import get_taught_student
from app.services.analytics_service import cohort_students, invalidate, refresh_students
from app.services.lifecycle_service import active_students, snapshot, record_change

router = APIRouter(prefix="/teacher", tags=["Teacher Operations"])
teacher = require_role(["TEACHER"])


def period(row):
    if isinstance(row, Assessment):
        return row.term, row.academic_year
    if isinstance(row, (Attendance, BehaviourRecord)):
        return term_for_date(row.record_date)
    return None


def subject_access(db, actor, student, subject):
    if not db.query(TeacherAssignment).filter_by(teacher_user_id=actor.user_id,
        grade_level=student.grade_level, stream=student.stream, subject_name=subject).first():
        raise HTTPException(status_code=403, detail="You are not assigned to this learner's subject.")


def correct(db, actor, model, record_id, data=None):
    row = db.get(model, record_id)
    if not row:
        raise HTTPException(status_code=404, detail="Record not found.")
    student = get_taught_student(db, actor, row.student_id)
    if isinstance(row, Assessment):
        subject_access(db, actor, student, row.subject_name)
    before = snapshot(row)
    old_period = period(row)
    if data is not None:
        if data.student_id != row.student_id:
            raise HTTPException(status_code=400, detail="A record cannot be moved to a different learner.")
        values = data.model_dump()
        if isinstance(row, Assessment):
            subject_access(db, actor, student, data.subject_name)
            if data.score > data.max_score:
                raise HTTPException(status_code=400, detail="Score cannot exceed maximum score.")
            try:
                term_date_range(data.term, data.academic_year)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            values["percentage"] = round(data.score / data.max_score * 100, 2)
        if isinstance(row, TeacherObservation):
            try:
                term_date_range(data.term, data.academic_year)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        for key, value in values.items():
            if key in ("assessment_date", "record_date", "observation_date") and value is None:
                continue  # Omitted dates retain the original date during correction.
            setattr(row, key, value)
        new_period = period(row)
        record_change(db, actor, row, "update", before)
    else:
        new_period = None
        record_change(db, actor, row, "delete", before)
        db.delete(row)
    periods = {p for p in (old_period, new_period) if p is not None}
    members = cohort_students(db, student) if model is Assessment else [student]
    for term, year in periods:
        invalidate(db, members, term, year)
    db.commit()  # Source changes and audit entry survive a later model failure.
    results = {f"{term} {year}": refresh_students(db, members, term, year) for term, year in periods}
    return {"message": "Record corrected." if data is not None else "Record removed. Correction history preserved.", "analytics_refresh": results}


@router.put("/assessments/{record_id}")
def update_assessment(record_id: int, data: AssessmentCreate, actor: User = Depends(teacher), db: Session = Depends(get_db)):
    return correct(db, actor, Assessment, record_id, data)

@router.delete("/assessments/{record_id}")
def delete_assessment(record_id: int, actor: User = Depends(teacher), db: Session = Depends(get_db)):
    return correct(db, actor, Assessment, record_id)

@router.put("/behaviour/{record_id}")
def update_behaviour(record_id: int, data: BehaviourCreate, actor: User = Depends(teacher), db: Session = Depends(get_db)):
    return correct(db, actor, BehaviourRecord, record_id, data)

@router.delete("/behaviour/{record_id}")
def delete_behaviour(record_id: int, actor: User = Depends(teacher), db: Session = Depends(get_db)):
    return correct(db, actor, BehaviourRecord, record_id)

@router.put("/observations/{record_id}")
def update_observation(record_id: int, data: TeacherObservationCreate, actor: User = Depends(teacher), db: Session = Depends(get_db)):
    return correct(db, actor, TeacherObservation, record_id, data)

@router.delete("/observations/{record_id}")
def delete_observation(record_id: int, actor: User = Depends(teacher), db: Session = Depends(get_db)):
    return correct(db, actor, TeacherObservation, record_id)

@router.delete("/attendance/{record_id}")
def delete_attendance(record_id: int, actor: User = Depends(teacher), db: Session = Depends(get_db)):
    return correct(db, actor, Attendance, record_id)


@router.get("/attendance", response_model=list[AttendanceOut])
def read_register(grade_level: str, stream: str, record_date: date,
                  actor: User = Depends(teacher), db: Session = Depends(get_db)):
    if not db.query(TeacherAssignment).filter_by(teacher_user_id=actor.user_id, grade_level=grade_level, stream=stream).first():
        raise HTTPException(status_code=403, detail="You are not assigned to this class.")
    return db.query(Attendance).join(Student, Student.student_id == Attendance.student_id).filter(
        Student.grade_level == grade_level, Student.stream == stream, active_students(),
        Attendance.record_date == record_date).order_by(Attendance.student_id).all()
