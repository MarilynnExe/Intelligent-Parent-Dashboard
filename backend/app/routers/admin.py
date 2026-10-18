"""
Admin Operations Router.

Exposes endpoints for:
    - System summary statistics
    - User account management (Admins, Teachers, Parents)
    - Student enrollment and roster management
    - Teacher class and subject assignments
    - Parent-learner relationship linking
"""

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_role
from app.core.security import hash_password
from app.models.academic import Assessment
from app.models.behaviour import Attendance
from app.models.student import ParentStudent, Student, TeacherAssignment
from app.models.user import User
from app.schemas.admin import (
    AdminStatsOut,
    ParentLinkCreate,
    ParentLinkDetailOut,
    StudentCreate,
    StudentOut,
    TeacherAssignmentCreate,
    TeacherAssignmentDetailOut,
    UserCreate,
    UserOut,
)

router = APIRouter(
    prefix="/admin",
    tags=["Admin Operations"],
)


# -----------------------------------------------------------------------------
# 1. System Statistics
# -----------------------------------------------------------------------------

@router.get("/stats", response_model=AdminStatsOut)
def get_system_stats(
    current_user: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    total_users = db.query(func.count(User.user_id)).scalar() or 0
    total_admins = db.query(func.count(User.user_id)).filter(User.role == "ADMIN").scalar() or 0
    total_teachers = db.query(func.count(User.user_id)).filter(User.role == "TEACHER").scalar() or 0
    total_parents = db.query(func.count(User.user_id)).filter(User.role == "PARENT").scalar() or 0
    total_students = db.query(func.count(Student.student_id)).scalar() or 0
    total_assessments = db.query(func.count(Assessment.assessment_id)).scalar() or 0
    total_attendance = db.query(func.count(Attendance.attendance_id)).scalar() or 0

    return AdminStatsOut(
        total_users=total_users,
        total_admins=total_admins,
        total_teachers=total_teachers,
        total_parents=total_parents,
        total_students=total_students,
        total_assessments=total_assessments,
        total_attendance_records=total_attendance,
    )


# -----------------------------------------------------------------------------
# 2. User Management
# -----------------------------------------------------------------------------

@router.get("/users", response_model=List[UserOut])
def list_users(
    current_user: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    return db.query(User).order_by(User.user_id.asc()).all()


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    data: UserCreate,
    current_user: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    role_upper = data.role.upper().strip()
    if role_upper not in ["ADMIN", "TEACHER", "PARENT"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role '{data.role}'. Role must be ADMIN, TEACHER, or PARENT.",
        )

    # Check for existing username/email
    existing = db.query(User).filter(User.email_or_username == data.email_or_username.strip()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with username/email '{data.email_or_username}' already exists.",
        )

    hashed = hash_password(data.password)

    user = User(
        full_name=data.full_name.strip(),
        email_or_username=data.email_or_username.strip(),
        password_hash=hashed,
        role=role_upper,
        phone_number=data.phone_number.strip() if data.phone_number else None,
        created_at=datetime.now(timezone.utc),
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


# -----------------------------------------------------------------------------
# 3. Student Records Management
# -----------------------------------------------------------------------------

@router.get("/students", response_model=List[StudentOut])
def list_students(
    current_user: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    return db.query(Student).order_by(Student.grade_level, Student.last_name).all()


@router.post("/students", response_model=StudentOut, status_code=status.HTTP_201_CREATED)
def enroll_student(
    data: StudentCreate,
    current_user: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    existing = db.query(Student).filter(Student.admission_number == data.admission_number.strip()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Student with admission number '{data.admission_number}' already exists.",
        )

    student = Student(
        admission_number=data.admission_number.strip(),
        first_name=data.first_name.strip(),
        last_name=data.last_name.strip(),
        date_of_birth=data.date_of_birth,
        gender=data.gender.strip() if data.gender else None,
        grade_level=data.grade_level.strip(),
        stream=data.stream.strip() if data.stream else None,
        created_at=datetime.now(timezone.utc),
    )

    db.add(student)
    db.commit()
    db.refresh(student)

    return student


# -----------------------------------------------------------------------------
# 4. Teacher Class Assignments
# -----------------------------------------------------------------------------

@router.get("/teacher-assignments", response_model=List[TeacherAssignmentDetailOut])
def list_teacher_assignments(
    current_user: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(TeacherAssignment, User.full_name)
        .join(User, TeacherAssignment.teacher_user_id == User.user_id)
        .order_by(TeacherAssignment.grade_level, TeacherAssignment.stream, User.full_name)
        .all()
    )

    return [
        TeacherAssignmentDetailOut(
            assignment_id=ta.assignment_id,
            teacher_user_id=ta.teacher_user_id,
            teacher_name=teacher_name,
            grade_level=ta.grade_level,
            stream=ta.stream,
            subject_name=ta.subject_name,
        )
        for ta, teacher_name in rows
    ]


@router.post("/teacher-assignments", response_model=TeacherAssignmentDetailOut, status_code=status.HTTP_201_CREATED)
def create_teacher_assignment(
    data: TeacherAssignmentCreate,
    current_user: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    teacher = db.query(User).filter(User.user_id == data.teacher_user_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher user not found.")
    if teacher.role != "TEACHER":
        raise HTTPException(status_code=400, detail="Specified user does not have TEACHER role.")

    # Check for duplicate assignment
    existing = db.query(TeacherAssignment).filter(
        TeacherAssignment.teacher_user_id == data.teacher_user_id,
        TeacherAssignment.grade_level == data.grade_level.strip(),
        TeacherAssignment.stream == data.stream.strip(),
        TeacherAssignment.subject_name == data.subject_name.strip(),
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="This teacher assignment already exists.")

    assignment = TeacherAssignment(
        teacher_user_id=data.teacher_user_id,
        grade_level=data.grade_level.strip(),
        stream=data.stream.strip(),
        subject_name=data.subject_name.strip(),
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    return TeacherAssignmentDetailOut(
        assignment_id=assignment.assignment_id,
        teacher_user_id=assignment.teacher_user_id,
        teacher_name=teacher.full_name,
        grade_level=assignment.grade_level,
        stream=assignment.stream,
        subject_name=assignment.subject_name,
    )


@router.delete("/teacher-assignments/{assignment_id}")
def delete_teacher_assignment(
    assignment_id: int,
    current_user: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    assignment = db.query(TeacherAssignment).filter(TeacherAssignment.assignment_id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found.")

    db.delete(assignment)
    db.commit()
    return {"message": f"Teacher assignment {assignment_id} successfully deleted."}


# -----------------------------------------------------------------------------
# 5. Parent-Student Linking
# -----------------------------------------------------------------------------

@router.get("/parent-links", response_model=List[ParentLinkDetailOut])
def list_parent_links(
    current_user: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(
            ParentStudent.id,
            ParentStudent.parent_user_id,
            User.full_name.label("parent_name"),
            ParentStudent.student_id,
            func.concat(Student.first_name, " ", Student.last_name).label("student_name"),
            Student.admission_number,
            ParentStudent.relationship_type,
        )
        .join(User, ParentStudent.parent_user_id == User.user_id)
        .join(Student, ParentStudent.student_id == Student.student_id)
        .order_by(User.full_name)
        .all()
    )

    return [
        ParentLinkDetailOut(
            id=r.id,
            parent_user_id=r.parent_user_id,
            parent_name=r.parent_name,
            student_id=r.student_id,
            student_name=r.student_name,
            admission_number=r.admission_number,
            relationship_type=r.relationship_type,
        )
        for r in rows
    ]


@router.post("/parent-links", response_model=ParentLinkDetailOut, status_code=status.HTTP_201_CREATED)
def link_parent_to_student(
    data: ParentLinkCreate,
    current_user: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    parent = db.query(User).filter(User.user_id == data.parent_user_id).first()
    if not parent:
        raise HTTPException(status_code=404, detail="Parent user not found.")
    if parent.role != "PARENT":
        raise HTTPException(status_code=400, detail="Specified user does not have PARENT role.")

    student = db.query(Student).filter(Student.student_id == data.student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")

    # Check for duplicate link
    existing = db.query(ParentStudent).filter(
        ParentStudent.parent_user_id == data.parent_user_id,
        ParentStudent.student_id == data.student_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="This parent-student link already exists.")

    link = ParentStudent(
        parent_user_id=data.parent_user_id,
        student_id=data.student_id,
        relationship_type=data.relationship_type.strip() if data.relationship_type else "Guardian",
    )
    db.add(link)
    db.commit()
    db.refresh(link)

    return ParentLinkDetailOut(
        id=link.id,
        parent_user_id=link.parent_user_id,
        parent_name=parent.full_name,
        student_id=link.student_id,
        student_name=f"{student.first_name} {student.last_name}",
        admission_number=student.admission_number,
        relationship_type=link.relationship_type,
    )


@router.delete("/parent-links/{link_id}")
def delete_parent_link(
    link_id: int,
    current_user: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    link = db.query(ParentStudent).filter(ParentStudent.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Parent-student link not found.")

    db.delete(link)
    db.commit()
    return {"message": f"Parent-student link {link_id} successfully removed."}
