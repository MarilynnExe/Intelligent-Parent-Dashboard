"""Administrative corrections and reversible account/learner lifecycle operations."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import require_role
from app.core.security import hash_password
from app.models.user import User
from app.models.student import Student, TeacherAssignment, ParentStudent
from app.models.lifecycle import UserLifecycle, StudentLifecycle, RecordChange
from app.models.academic import Assessment
from app.models.analytics import StudentAnalytics
from app.schemas.admin import (UserUpdate, UserOut, StudentCreate, StudentOut,
    ActiveUpdate, ArchiveUpdate, TeacherAssignmentCreate, TeacherAssignmentDetailOut,
    ParentLinkCreate, ParentLinkDetailOut)
from app.services.lifecycle_service import (active_users, active_students, user_state, archived,
    snapshot, record_change, require_active_student)
from app.services.analytics_service import cohort_students, invalidate, refresh_students
from app.services.assignment_service import sync_new_learner

router = APIRouter(prefix="/admin", tags=["Admin Operations"])
admin = require_role(["ADMIN"])


def get_user(db, user_id):
    row = db.get(User, user_id)
    if not row:
        raise HTTPException(status_code=404, detail="User not found.")
    return row


def protect_admin(db, row, actor, removes_admin):
    if removes_admin and row.role == "ADMIN" and db.query(User).filter(User.user_id == row.user_id, active_users()).first():
        if db.query(User).filter(User.role == "ADMIN", active_users()).count() <= 1:
            raise HTTPException(status_code=409, detail="The last active administrator cannot be removed or demoted.")


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, data: UserUpdate, actor: User = Depends(admin), db: Session = Depends(get_db)):
    row = get_user(db, user_id)
    role = data.role.upper().strip()
    if role not in ("ADMIN", "TEACHER", "PARENT"):
        raise HTTPException(status_code=400, detail="Invalid role.")
    if db.query(User).filter(User.email_or_username == data.email_or_username, User.user_id != user_id).first():
        raise HTTPException(status_code=409, detail="Username/email already exists.")
    if role != row.role:
        protect_admin(db, row, actor, True)
        if db.query(TeacherAssignment).filter_by(teacher_user_id=user_id).first() or db.query(ParentStudent).filter_by(parent_user_id=user_id).first():
            raise HTTPException(status_code=409, detail="Remove this user's teaching assignments or parent links before changing their role.")
    before = snapshot(row)
    state = user_state(db, user_id)
    if data.password or role != row.role:
        state.token_version += 1
    for key in ("full_name", "email_or_username", "phone_number"):
        setattr(row, key, getattr(data, key))
    row.role = role
    if data.password:
        row.password_hash = hash_password(data.password)
    record_change(db, actor, row, "update", before)
    db.commit()
    return UserOut.model_validate(row).model_copy(update={"is_active": state.is_active})


def change_user_status(db, row, actor, is_active):
    state = user_state(db, row.user_id)
    if not is_active:
        if actor.user_id == row.user_id:
            raise HTTPException(status_code=409, detail="You cannot deactivate your own account.")
        protect_admin(db, row, actor, True)
    before = {**snapshot(row), "is_active": state.is_active}
    if state.is_active != is_active:
        state.token_version += 1
        state.is_active = is_active
        record_change(db, actor, row, "restore" if is_active else "deactivate", before)
    db.commit()
    return {"message": "Account restored." if is_active else "Account deactivated. History preserved.", "is_active": is_active}


@router.delete("/users/{user_id}")
def deactivate_user(user_id: int, actor: User = Depends(admin), db: Session = Depends(get_db)):
    return change_user_status(db, get_user(db, user_id), actor, False)


@router.patch("/users/{user_id}/status")
def restore_user(user_id: int, data: ActiveUpdate, actor: User = Depends(admin), db: Session = Depends(get_db)):
    return change_user_status(db, get_user(db, user_id), actor, data.is_active)


def student_refresh_plan(db, members):
    ids = {s.student_id for s in members}
    periods = set(db.query(Assessment.term, Assessment.academic_year).filter(Assessment.student_id.in_(ids)).distinct().all())
    periods.update(db.query(StudentAnalytics.term, StudentAnalytics.academic_year).filter(StudentAnalytics.student_id.in_(ids)).distinct().all())
    for term, year in periods:
        invalidate(db, members, term, year)
    return periods


def finish_student_change(db, members, periods):
    active = [s for s in members if not archived(db, s.student_id)]
    return {f"{term} {year}": refresh_students(db, active, term, year) for term, year in periods}


@router.put("/students/{student_id}", response_model=StudentOut)
def update_student(student_id: int, data: StudentCreate, actor: User = Depends(admin), db: Session = Depends(get_db)):
    row = db.get(Student, student_id)
    if not row:
        raise HTTPException(status_code=404, detail="Student not found.")
    if db.query(Student).filter(Student.admission_number == data.admission_number, Student.student_id != student_id).first():
        raise HTTPException(status_code=409, detail="Admission number already exists.")
    before = snapshot(row)
    old = cohort_students(db, row)
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    db.flush()
    sync_new_learner(db, row)
    members = list({s.student_id: s for s in old + cohort_students(db, row) + [row]}.values())
    periods = student_refresh_plan(db, members)
    record_change(db, actor, row, "update", before)
    db.commit()
    finish_student_change(db, members, periods)
    return StudentOut.model_validate(row).model_copy(update={"is_archived": archived(db, student_id)})


def change_student_status(db, row, actor, is_archived):
    members = cohort_students(db, row)
    state = db.get(StudentLifecycle, row.student_id)
    if state is None:
        state = StudentLifecycle(student_id=row.student_id, is_archived=False)
        db.add(state)
    before = {**snapshot(row), "is_archived": state.is_archived}
    state.is_archived = is_archived
    db.flush()
    if not is_archived:
        sync_new_learner(db, row)
    members = list({s.student_id: s for s in members + cohort_students(db, row) + [row]}.values())
    periods = student_refresh_plan(db, members)
    record_change(db, actor, row, "archive" if is_archived else "restore", before)
    db.commit()
    results = finish_student_change(db, members, periods)
    return {"message": "Learner archived. History preserved." if is_archived else "Learner restored.", "is_archived": is_archived, "analytics_refresh": results}


@router.delete("/students/{student_id}")
def archive_student(student_id: int, actor: User = Depends(admin), db: Session = Depends(get_db)):
    row = db.get(Student, student_id)
    if not row:
        raise HTTPException(status_code=404, detail="Student not found.")
    return change_student_status(db, row, actor, True)


@router.patch("/students/{student_id}/status")
def restore_student(student_id: int, data: ArchiveUpdate, actor: User = Depends(admin), db: Session = Depends(get_db)):
    row = db.get(Student, student_id)
    if not row:
        raise HTTPException(status_code=404, detail="Student not found.")
    return change_student_status(db, row, actor, data.is_archived)


def require_role_user(db, user_id, role):
    user = get_user(db, user_id)
    if user.role != role or not db.query(User).filter(User.user_id == user_id, active_users()).first():
        raise HTTPException(status_code=400, detail=f"An active {role.lower()} account is required.")
    return user


@router.put("/teacher-assignments/{assignment_id}", response_model=TeacherAssignmentDetailOut)
def update_assignment(assignment_id: int, data: TeacherAssignmentCreate, actor: User = Depends(admin), db: Session = Depends(get_db)):
    row = db.get(TeacherAssignment, assignment_id)
    if not row:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    teacher = require_role_user(db, data.teacher_user_id, "TEACHER")
    if db.query(TeacherAssignment).filter_by(**data.model_dump()).filter(TeacherAssignment.assignment_id != assignment_id).first():
        raise HTTPException(status_code=409, detail="Teacher assignment already exists.")
    before = snapshot(row)
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    record_change(db, actor, row, "update", before)
    db.commit()
    return {**snapshot(row), "teacher_name": teacher.full_name}


@router.put("/parent-links/{link_id}", response_model=ParentLinkDetailOut)
def update_link(link_id: int, data: ParentLinkCreate, actor: User = Depends(admin), db: Session = Depends(get_db)):
    row = db.get(ParentStudent, link_id)
    if not row:
        raise HTTPException(status_code=404, detail="Parent link not found.")
    parent = require_role_user(db, data.parent_user_id, "PARENT")
    student = db.get(Student, data.student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")
    require_active_student(db, student)
    if db.query(ParentStudent).filter_by(parent_user_id=data.parent_user_id, student_id=data.student_id).filter(ParentStudent.id != link_id).first():
        raise HTTPException(status_code=409, detail="Parent link already exists.")
    before = snapshot(row)
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    record_change(db, actor, row, "update", before)
    db.commit()
    return {**snapshot(row), "parent_name": parent.full_name, "student_name": f"{student.first_name} {student.last_name}", "admission_number": student.admission_number}


@router.get("/change-history")
def change_history(entity_type: str, entity_id: int, actor: User = Depends(admin), db: Session = Depends(get_db)):
    rows = db.query(RecordChange).filter_by(entity_type=entity_type, entity_id=entity_id).order_by(RecordChange.change_id.desc()).limit(100).all()
    return [{"change_id": r.change_id, "actor_user_id": r.actor_user_id, "action": r.action,
             "changed_at": r.changed_at, "before": r.before_json, "after": r.after_json} for r in rows]
