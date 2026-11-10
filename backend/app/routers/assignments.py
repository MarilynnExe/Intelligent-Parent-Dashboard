"""Class-work tracking, separate from teaching assignments and scored assessments."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import require_role
from app.core.academic_calendar import term_date_range, term_for_date
from app.models.assignment import ClassAssignment, AssignmentCompletion
from app.models.student import Student, ParentStudent, TeacherAssignment
from app.models.user import User
from app.schemas.assignment import (AssignmentCreate, AssignmentDetails, AssignmentOut,
    AssignmentStatusUpdate, AssignmentRegisterOut, CompletionBulkUpdate, AssignmentSummaryOut)
from app.services import assignment_service as service
from app.services.lifecycle_service import active_students, require_active_student, snapshot, record_change

router = APIRouter(tags=["Assignment Completion"])
teacher = require_role(["TEACHER"])


def get_assignment(db, assignment_id, actor):
    row = db.get(ClassAssignment, assignment_id)
    if not row:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    service.assignment_access(db, actor, row)
    return row


def recipients(db, assignment_id):
    return db.query(AssignmentCompletion).filter_by(assignment_id=assignment_id).all()


def notifications(db, assignment):
    return service.notify_follow_up(db, [r.student_id for r in recipients(db, assignment.assignment_id)],
                                   assignment.term, assignment.academic_year)


@router.get("/teacher/class-assignments", response_model=list[AssignmentOut])
def list_assignments(grade_level: str, stream: str, subject_name: str, term: str, academic_year: str,
                     include_withdrawn: bool = False, actor: User = Depends(teacher), db: Session = Depends(get_db)):
    if not db.query(TeacherAssignment).filter_by(teacher_user_id=actor.user_id,
        grade_level=grade_level, stream=stream, subject_name=subject_name).first():
        raise HTTPException(status_code=403, detail="You are not assigned to this class and subject.")
    query = db.query(ClassAssignment).filter_by(grade_level=grade_level, stream=stream,
        subject_name=subject_name, term=term, academic_year=academic_year)
    if not include_withdrawn:
        query = query.filter(ClassAssignment.is_withdrawn.is_(False))
    return query.order_by(ClassAssignment.due_date.desc(), ClassAssignment.assignment_id.desc()).all()


@router.post("/teacher/class-assignments", response_model=AssignmentOut, status_code=201)
def create_assignment(data: AssignmentCreate, actor: User = Depends(teacher), db: Session = Depends(get_db)):
    row = ClassAssignment(**data.model_dump(), created_by_teacher_id=actor.user_id)
    service.assignment_access(db, actor, row)
    db.add(row)
    db.flush()
    # Initial recipients include the current class, even when entering historical work.
    for student in db.query(Student).filter(active_students()).filter_by(grade_level=row.grade_level, stream=row.stream).all():
        service.add_recipient(db, row, student)
    record_change(db, actor, row, "create")
    db.commit()
    row.notification_delivery = notifications(db, row)
    return row


@router.put("/teacher/class-assignments/{assignment_id}", response_model=AssignmentOut)
def update_assignment(assignment_id: int, data: AssignmentDetails, actor: User = Depends(teacher), db: Session = Depends(get_db)):
    row = get_assignment(db, assignment_id, actor)
    if row.is_withdrawn:
        raise HTTPException(status_code=409, detail="Restore this assignment before editing it.")
    start, end = term_date_range(row.term, row.academic_year)
    if not (start <= data.assigned_date <= data.due_date <= end):
        raise HTTPException(status_code=400, detail="Dates must remain within the assignment's term/year.")
    for entry in recipients(db, assignment_id):
        if entry.status == "SUBMITTED":
            if entry.submitted_on < data.assigned_date:
                raise HTTPException(status_code=409, detail="Assigned date cannot follow an existing submission date.")
            if entry.submitted_on > data.due_date and not entry.reason:
                raise HTTPException(status_code=409, detail="Add late reasons before moving the deadline earlier than existing submissions.")
    before = snapshot(row)
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    db.flush()
    service.sync_assignment_roster(db, row)
    record_change(db, actor, row, "update", before)
    db.commit()
    row.notification_delivery = notifications(db, row)
    return row


def set_withdrawn(db, actor, row, withdrawn):
    before = snapshot(row)
    row.is_withdrawn = withdrawn
    db.flush()
    if not withdrawn:
        service.sync_assignment_roster(db, row)
    record_change(db, actor, row, "withdraw" if withdrawn else "restore", before)
    db.commit()
    delivery = notifications(db, row)
    return {"message": "Assignment withdrawn. History preserved." if withdrawn else "Assignment restored.",
            "is_withdrawn": withdrawn, "notification_delivery": delivery}


@router.delete("/teacher/class-assignments/{assignment_id}")
def withdraw_assignment(assignment_id: int, actor: User = Depends(teacher), db: Session = Depends(get_db)):
    return set_withdrawn(db, actor, get_assignment(db, assignment_id, actor), True)


@router.patch("/teacher/class-assignments/{assignment_id}/status")
def restore_assignment(assignment_id: int, data: AssignmentStatusUpdate, actor: User = Depends(teacher), db: Session = Depends(get_db)):
    return set_withdrawn(db, actor, get_assignment(db, assignment_id, actor), data.is_withdrawn)


@router.get("/teacher/class-assignments/{assignment_id}/register", response_model=AssignmentRegisterOut)
def get_register(assignment_id: int, actor: User = Depends(teacher), db: Session = Depends(get_db)):
    row = get_assignment(db, assignment_id, actor)
    records = db.query(AssignmentCompletion, Student).join(Student, Student.student_id == AssignmentCompletion.student_id).filter(
        AssignmentCompletion.assignment_id == assignment_id).order_by(Student.last_name, Student.first_name).all()
    return {"assignment": row, "as_of": service.school_today(), "recipients": [
        {"completion_id": entry.completion_id, "student_id": student.student_id,
         "student_name": f"{student.first_name} {student.last_name}", "admission_number": student.admission_number,
         "status": entry.status, "display_status": service.display_status(row, entry),
         "submitted_on": entry.submitted_on, "reason": entry.reason, "updated_at": entry.updated_at,
         "editable": service.recipient_editable(db, row, student)} for entry, student in records]}


@router.put("/teacher/class-assignments/{assignment_id}/completions")
def save_completions(assignment_id: int, data: CompletionBulkUpdate, actor: User = Depends(teacher), db: Session = Depends(get_db)):
    row = get_assignment(db, assignment_id, actor)
    if row.is_withdrawn:
        raise HTTPException(status_code=409, detail="Restore the assignment before recording completion.")
    by_student = {entry.student_id: entry for entry in recipients(db, assignment_id)}
    # Validate every entry before modifying any record.
    for entry in data.entries:
        completion = by_student.get(entry.student_id)
        student = db.get(Student, entry.student_id)
        if completion is None or student is None:
            raise HTTPException(status_code=400, detail="Learner is not a recipient of this assignment.")
        if not service.recipient_editable(db, row, student):
            raise HTTPException(status_code=403, detail="Archived or transferred recipients are read-only.")
        service.validate_submission(row, entry)
    for entry in data.entries:
        completion = by_student[entry.student_id]
        before = snapshot(completion)
        completion.status, completion.submitted_on, completion.reason = entry.status, entry.submitted_on, entry.reason or None
        completion.recorded_by_teacher_id = actor.user_id
        completion.updated_at = datetime.utcnow()
        record_change(db, actor, completion, "update", before)
    db.commit()
    delivery = notifications(db, row)
    return {"message": "Completion register saved.", "updated": len(data.entries), "notification_delivery": delivery}


@router.post("/teacher/class-assignments/{assignment_id}/notify")
def retry_notifications(assignment_id: int, actor: User = Depends(teacher), db: Session = Depends(get_db)):
    row = get_assignment(db, assignment_id, actor)
    return notifications(db, row)


@router.get("/parent/children/{student_id}/assignments", response_model=AssignmentSummaryOut)
def parent_assignments(student_id: int, term: str | None = None, academic_year: str | None = None,
                       include_withdrawn: bool = False, actor: User = Depends(require_role(["PARENT", "ADMIN"])),
                       db: Session = Depends(get_db)):
    student = db.get(Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")
    if actor.role == "PARENT":
        if not db.query(ParentStudent).filter_by(parent_user_id=actor.user_id, student_id=student_id).first():
            raise HTTPException(status_code=403, detail="You are not linked to this learner.")
        require_active_student(db, student)
    current_term, current_year = term_for_date(service.school_today())
    term, academic_year = term or current_term, academic_year or current_year
    try:
        term_date_range(term, academic_year)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return service.summary(db, student_id, term, academic_year, include_withdrawn)
