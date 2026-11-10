"""
Parent Operations Router.

Exposes endpoints for:
    - Listing verified children linked to the logged-in parent
    - Querying assessments for a linked child
"""

from typing import List
from datetime import date
from collections import Counter, defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_role
from app.models.academic import Assessment
from app.models.student import ParentStudent, Student
from app.models.user import User
from app.services.lifecycle_service import active_students, require_active_student
from app.schemas.academic import AssessmentOut
from app.schemas.parent import ChildSummaryOut, LearnerProgressOut
from app.core.academic_calendar import term_date_range, term_for_date
from app.models.analytics import AnalyticsFreshness, StudentAnalytics
from app.models.behaviour import Attendance

router = APIRouter(
    prefix="/parent",
    tags=["Parent Operations"],
)


@router.get(
    "/my-children",
    response_model=List[ChildSummaryOut],
)
def get_my_children(
    current_user: User = Depends(require_role(["PARENT", "ADMIN"])),
    db: Session = Depends(get_db),
):
    """
    Retrieve list of learners linked to the logged-in parent via ParentStudent relationship.
    """
    results = (
        db.query(Student, ParentStudent.relationship_type)
        .join(ParentStudent, Student.student_id == ParentStudent.student_id)
        .filter(ParentStudent.parent_user_id == current_user.user_id, active_students())
        .order_by(Student.last_name, Student.first_name)
        .all()
    )

    children = []
    for student, rel in results:
        children.append(
            ChildSummaryOut(
                student_id=student.student_id,
                admission_number=student.admission_number,
                first_name=student.first_name,
                last_name=student.last_name,
                date_of_birth=student.date_of_birth,
                gender=student.gender,
                grade_level=student.grade_level,
                stream=student.stream,
                relationship_type=rel,
            )
        )

    return children


@router.get(
    "/children/{student_id}/assessments",
    response_model=List[AssessmentOut],
)
def get_child_assessments(
    student_id: int,
    current_user: User = Depends(require_role(["PARENT", "ADMIN"])),
    db: Session = Depends(get_db),
):
    """
    Retrieve assessment history for a parent's verified child.
    """
    student = db.get(Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")
    if current_user.role == "PARENT":
        require_active_student(db, student)
        authorized = (
            db.query(ParentStudent)
            .filter(
                ParentStudent.parent_user_id == current_user.user_id,
                ParentStudent.student_id == student_id,
            )
            .first()
        )
        if not authorized:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to view this student's assessment records.",
            )

    return (
        db.query(Assessment)
        .filter(Assessment.student_id == student_id)
        .order_by(Assessment.assessment_date.desc())
        .all()
    )


@router.get("/children/{student_id}/progress", response_model=LearnerProgressOut)
def get_child_progress(
    student_id: int, term: str | None = None, academic_year: str | None = None,
    current_user: User = Depends(require_role(["PARENT", "ADMIN"])),
    db: Session = Depends(get_db),
):
    student = db.get(Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")
    if current_user.role == "PARENT":
        require_active_student(db, student)
    if current_user.role == "PARENT" and not db.query(ParentStudent).filter_by(
        parent_user_id=current_user.user_id, student_id=student_id).first():
        raise HTTPException(status_code=403, detail="Unauthorized learner access.")
    current_term, current_year = term_for_date(date.today())
    term, academic_year = term or current_term, academic_year or current_year
    try:
        start, end = term_date_range(term, academic_year)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    assessments = db.query(Assessment).filter_by(student_id=student_id, term=term,
        academic_year=academic_year).order_by(Assessment.assessment_date, Assessment.assessment_id).all()
    records = db.query(Attendance).filter(Attendance.student_id == student_id,
        Attendance.record_date >= start, Attendance.record_date <= end).order_by(Attendance.record_date).all()
    totals = Counter({"Present": 0, "Absent": 0, "Late": 0, "Excused": 0})
    months = defaultdict(Counter)
    for record in records:
        totals[record.status] += 1
        months[record.record_date.strftime("%Y-%m")][record.status] += 1
    freshness = db.query(AnalyticsFreshness).filter_by(student_id=student_id, term=term,
        academic_year=academic_year).first()
    analytics = db.query(StudentAnalytics).filter_by(student_id=student_id, term=term,
        academic_year=academic_year).first()
    return {
        "student_id": student_id, "term": term, "academic_year": academic_year,
        "assessments": assessments,
        "overall_average": round(sum(a.percentage for a in assessments) / len(assessments), 2) if assessments else None,
        "attendance_totals": {**totals, "recorded": len(records)},
        "attendance_months": [{"month": month, "recorded": sum(counts.values()),
            **{key.lower(): counts[key] for key in ("Present", "Absent", "Late", "Excused")}}
            for month, counts in sorted(months.items())],
        "freshness": freshness.state if freshness else ("stale" if analytics else "pending"),
        "freshness_message": freshness.message if freshness else "Ask the teacher to calculate analytics for this period.",
        "calculated_at": analytics.calculated_at if analytics else None,
    }
