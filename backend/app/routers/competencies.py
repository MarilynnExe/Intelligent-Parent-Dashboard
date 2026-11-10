"""Authorized competency catalog CRUD and dated learner evidence."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import require_role
from app.core.academic_calendar import term_date_range
from app.models.competency import Competency, CompetencyObservation
from app.models.student import Student, ParentStudent
from app.schemas.competency import CompetencyCreate, CompetencyDetails, CompetencyStatus, ObservationCreate, ObservationDetails
from app.services import competency_service as service
from app.services.lifecycle_service import active_students, require_active_student, snapshot, record_change

router = APIRouter(tags=["Competency Tracking"])
teacher = require_role(["TEACHER"])

def get_skill(db, actor, key):
    row = db.get(Competency, key)
    if not row:
        raise HTTPException(status_code=404, detail="Competency not found.")
    service.access(db, actor, row)
    return row

def get_observation(db, actor, key):
    row = db.get(CompetencyObservation, key)
    if not row:
        raise HTTPException(status_code=404, detail="Observation not found.")
    skill = get_skill(db, actor, row.competency_id)
    if skill.is_archived:
        raise HTTPException(status_code=409, detail="Restore this competency before editing its observations.")
    student = service.learner_access(db, skill, row.student_id)
    return row, student

def check_period(term, academic_year):
    try:
        term_date_range(term, academic_year)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.get("/teacher/competencies")
def catalog(grade_level: str, stream: str, subject_name: str, include_archived: bool = False,
    actor=Depends(teacher), db: Session=Depends(get_db)):
    service.access(db, actor, Competency(grade_level=grade_level, stream=stream, subject_name=subject_name))
    query = db.query(Competency).filter_by(grade_level=grade_level, stream=stream, subject_name=subject_name)
    if not include_archived:
        query = query.filter_by(is_archived=False)
    return [snapshot(r) for r in query.order_by(Competency.strand, Competency.name, Competency.competency_id).all()]

@router.post("/teacher/competencies", status_code=201)
def create(data: CompetencyCreate, actor=Depends(teacher), db: Session=Depends(get_db)):
    row = Competency(**data.model_dump(), created_by_teacher_id=actor.user_id)
    service.access(db, actor, row)
    db.add(row); db.flush(); record_change(db, actor, row, "create"); db.commit()
    return snapshot(row)

@router.put("/teacher/competencies/{competency_id}")
def update(competency_id: int, data: CompetencyDetails, actor=Depends(teacher), db: Session=Depends(get_db)):
    row = get_skill(db, actor, competency_id)
    if row.is_archived:
        raise HTTPException(status_code=409, detail="Restore this competency before editing it.")
    before = snapshot(row)
    for key, value in data.model_dump().items(): setattr(row, key, value)
    record_change(db, actor, row, "update", before); db.commit()
    return {**snapshot(row), "notification_delivery": notify_skill_periods(db, row)}

def notify_skill_periods(db, row):
    # Resolve/rebuild existing follow-ups for every affected learner and period.
    periods = db.query(CompetencyObservation.student_id, CompetencyObservation.term, CompetencyObservation.academic_year).filter_by(competency_id=row.competency_id).distinct().all()
    failed = False
    for sid, term, year in periods:
        if service.notify(db, db.get(Student, sid), term, year)["status"] == "retry_needed": failed = True
    return {"status": "retry_needed" if failed else "complete"}

def archive(db, actor, row, value):
    before = snapshot(row); row.is_archived = value
    record_change(db, actor, row, "archive" if value else "restore", before); db.commit()
    return {**snapshot(row), "notification_delivery": notify_skill_periods(db, row)}

@router.delete("/teacher/competencies/{competency_id}")
def remove(competency_id: int, actor=Depends(teacher), db: Session=Depends(get_db)):
    return archive(db, actor, get_skill(db, actor, competency_id), True)

@router.patch("/teacher/competencies/{competency_id}/status")
def status(competency_id: int, data: CompetencyStatus, actor=Depends(teacher), db: Session=Depends(get_db)):
    return archive(db, actor, get_skill(db, actor, competency_id), data.is_archived)

@router.get("/teacher/competencies/{competency_id}/register")
def register(competency_id: int, term: str, academic_year: str, actor=Depends(teacher), db: Session=Depends(get_db)):
    skill = get_skill(db, actor, competency_id); check_period(term, academic_year)
    students = db.query(Student).filter(active_students()).filter_by(grade_level=skill.grade_level, stream=skill.stream).order_by(Student.first_name).all()
    history = db.query(CompetencyObservation).filter_by(competency_id=competency_id, term=term, academic_year=academic_year).order_by(CompetencyObservation.observed_on.desc(), CompetencyObservation.observation_id.desc()).all()
    return {"competency": snapshot(skill), "learners": [{"student_id": s.student_id, "name": f"{s.first_name} {s.last_name}",
        "observations": [snapshot(r) for r in history if r.student_id == s.student_id]} for s in students]}

@router.post("/teacher/competencies/{competency_id}/observations", status_code=201)
def observe(competency_id: int, data: ObservationCreate, actor=Depends(teacher), db: Session=Depends(get_db)):
    skill = get_skill(db, actor, competency_id)
    if skill.is_archived:
        raise HTTPException(status_code=409, detail="Restore this competency before recording evidence.")
    student = service.learner_access(db, skill, data.student_id); service.validate_date(data)
    row = CompetencyObservation(**data.model_dump(), competency_id=competency_id, recorded_by_teacher_id=actor.user_id)
    db.add(row); db.flush(); record_change(db, actor, row, "create"); db.commit()
    return {**snapshot(row), "notification_delivery": service.notify(db, student, row.term, row.academic_year)}

@router.put("/teacher/competency-observations/{observation_id}")
def correct(observation_id: int, data: ObservationDetails, actor=Depends(teacher), db: Session=Depends(get_db)):
    row, student = get_observation(db, actor, observation_id); service.validate_date(data)
    before = snapshot(row); old_period = row.term, row.academic_year
    for key, value in data.model_dump().items(): setattr(row, key, value)
    row.recorded_by_teacher_id, row.updated_at = actor.user_id, datetime.utcnow()
    record_change(db, actor, row, "update", before); db.commit()
    deliveries = [service.notify(db, student, *period) for period in set([old_period, (row.term, row.academic_year)])]
    return {**snapshot(row), "notification_delivery": {"status": "retry_needed" if any(d["status"] == "retry_needed" for d in deliveries) else "complete"}}

@router.delete("/teacher/competency-observations/{observation_id}")
def delete(observation_id: int, actor=Depends(teacher), db: Session=Depends(get_db)):
    row, student = get_observation(db, actor, observation_id); period = row.term, row.academic_year
    record_change(db, actor, row, "delete", snapshot(row)); db.delete(row); db.commit()
    return {"message": "Observation deleted; correction history retained.", "notification_delivery": service.notify(db, student, *period)}

@router.post("/teacher/competencies/{competency_id}/notify")
def retry(competency_id: int, term: str, academic_year: str, actor=Depends(teacher), db: Session=Depends(get_db)):
    skill = get_skill(db, actor, competency_id); check_period(term, academic_year)
    ids = db.query(CompetencyObservation.student_id).filter_by(competency_id=competency_id, term=term, academic_year=academic_year).distinct().all()
    failed = any([service.notify(db, db.get(Student, sid), term, academic_year)["status"] == "retry_needed" for (sid,) in ids])
    return {"status": "retry_needed" if failed else "complete"}

@router.get("/parent/children/{student_id}/competencies")
def parent_summary(student_id: int, term: str, academic_year: str,
    actor=Depends(require_role(["PARENT", "ADMIN"])), db: Session=Depends(get_db)):
    student = db.get(Student, student_id)
    if not student: raise HTTPException(status_code=404, detail="Learner not found.")
    if actor.role == "PARENT":
        if not db.query(ParentStudent).filter_by(parent_user_id=actor.user_id, student_id=student_id).first():
            raise HTTPException(status_code=403, detail="You are not linked to this learner.")
        require_active_student(db, student)
    check_period(term, academic_year)
    return service.summary(db, student, term, academic_year)
