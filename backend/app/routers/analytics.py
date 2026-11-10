"""
Analytics and Risk Prediction Router.

Exposes endpoints for:
    - Calculating early-warning student academic risk via CatBoost ML-3 pipeline
    - Generating transparent pedagogical recommendations via the Expert System
    - Querying student risk status and analytics for teachers and parents
"""

from __future__ import annotations

import logging
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.academic_calendar import term_date_range, term_for_date
from app.core.database import get_db
from app.services.lifecycle_service import require_active_student
from app.core.dependencies import get_current_user, require_role
from app.models.academic import CohortPercentile
from app.models.analytics import AnalyticsFreshness, Recommendation, StudentAnalytics
from app.models.student import ParentStudent, Student, TeacherAssignment
from app.models.user import User
from app.schemas.analytics import (
    CalculateAnalyticsRequest,
    LearningPathItemOut,
    LearningResourceOut,
    RecommendationOut,
    StudentAnalyticsOut,
)
from app.models.learning_path import LearningResource
from app.services.learning_path_service import LearningPathService
from app.services.analytics_service import cohort_students, count_term_absences, invalidate, refresh_students

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/analytics",
    tags=["Analytics & Early Intervention"],
)


def verify_student_access(
    current_user: User,
    student: Student,
    db: Session,
    allow_parent: bool = True,
) -> None:
    """
    Enforce authorization rules:
    - Admin: Full access.
    - Teacher: Must be assigned to student's grade_level and stream.
    - Parent: Must be registered as student's parent (if allow_parent is True).
    """
    if current_user.role != "ADMIN":
        require_active_student(db, student)
    if current_user.role == "ADMIN":
        return

    if current_user.role == "TEACHER":
        authorized = (
            db.query(TeacherAssignment)
            .filter(
                TeacherAssignment.teacher_user_id == current_user.user_id,
                TeacherAssignment.grade_level == student.grade_level,
                TeacherAssignment.stream == student.stream,
            )
            .first()
        )
        if not authorized:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to access this student's analytics.",
            )
        return

    if current_user.role == "PARENT" and allow_parent:
        authorized = (
            db.query(ParentStudent)
            .filter(
                ParentStudent.parent_user_id == current_user.user_id,
                ParentStudent.student_id == student.student_id,
            )
            .first()
        )
        if not authorized:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to view this student's analytics.",
            )
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient permissions to access student analytics.",
    )


@router.post(
    "/calculate/{student_id}",
    response_model=StudentAnalyticsOut,
    status_code=status.HTTP_200_OK,
)
def calculate_student_analytics(
    student_id: int,
    request: Optional[CalculateAnalyticsRequest] = None,
    current_user: User = Depends(require_role(["TEACHER", "ADMIN"])),
    db: Session = Depends(get_db),
):
    """
    Execute the ML-3 Early-Warning CatBoost pipeline for a student:
        1. Derive first_term_pct from Period 1 assessments.
        2. Derive cohort_percentile from class cohort reference distribution.
        3. Map period absences to benchmark horizon.
        4. Predict calibrated risk probability via CatBoost + Platt calibrator.
        5. Trigger Expert System rules to generate actionable recommendations.
    """
    # Unspecified term/year means the term today's date falls in.
    current_term, current_year = term_for_date(date.today())
    term = (request.term if request else None) or current_term
    academic_year = (request.academic_year if request else None) or current_year

    student = db.query(Student).filter(Student.student_id == student_id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with ID {student_id} not found.",
        )

    require_active_student(db, student)
    verify_student_access(current_user, student, db, allow_parent=False)

    try:
        term_date_range(term, academic_year)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    affected = cohort_students(db, student)
    invalidate(db, affected, term, academic_year)
    db.commit()
    results = refresh_students(db, affected, term, academic_year)
    result = results[student_id]
    if result["status"] != "current":
        raise HTTPException(status_code=400 if result["status"] == "pending" else 503,
                            detail=result["message"])
    return get_student_analytics(student_id, term, academic_year, current_user, db)


@router.get(
    "/student/{student_id}",
    response_model=StudentAnalyticsOut,
)
def get_student_analytics(
    student_id: int,
    term: Optional[str] = Query(None, description="Academic term; omit for the latest calculated"),
    academic_year: Optional[str] = Query(None, description="Academic year; omit for the latest calculated"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve stored analytics and active recommendations for a learner.
    Accessible to assigned teachers, parents of the student, and administrators.
    """
    student = db.query(Student).filter(Student.student_id == student_id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with ID {student_id} not found.",
        )

    verify_student_access(current_user, student, db, allow_parent=True)

    query = db.query(StudentAnalytics).filter(StudentAnalytics.student_id == student_id)
    if term:
        query = query.filter(StudentAnalytics.term == term)
    if academic_year:
        query = query.filter(StudentAnalytics.academic_year == academic_year)
    analytics = query.order_by(StudentAnalytics.calculated_at.desc()).first()

    if not analytics:
        period = " ".join(p for p in (term, academic_year) if p) or "any term"
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analytics not yet calculated for student {student_id} in {period}.",
        )

    freshness = db.query(AnalyticsFreshness).filter_by(
        student_id=student_id, term=analytics.term, academic_year=analytics.academic_year).first()
    is_current = freshness is not None and freshness.state == "current"

    # Everything below describes the period the analytics were calculated for.
    term, academic_year = analytics.term, analytics.academic_year

    recs = (
        db.query(Recommendation)
        .filter(
            Recommendation.student_id == student_id,
            Recommendation.term == term,
            Recommendation.academic_year == academic_year,
            Recommendation.status == "Active",
        )
        .order_by(Recommendation.generated_at.desc())
        .all()
    )

    cohort_record = (
        db.query(CohortPercentile)
        .filter(
            CohortPercentile.student_id == student_id,
            CohortPercentile.subject_name.is_(None),
            CohortPercentile.term == term,
            CohortPercentile.academic_year == academic_year,
        )
        .first()
    )
    cohort_percentile = float(cohort_record.percentile_rank) if cohort_record else None

    absences_count = count_term_absences(db, student_id, term, academic_year)

    learning_paths = LearningPathService.get_student_learning_path(
        db, student_id, term=term, academic_year=academic_year, active_only=True
    )
    lp_by_rec = {lp.recommendation_id: LearningPathItemOut.model_validate(lp) for lp in learning_paths if lp.recommendation_id}

    formatted_recs = []
    for r in recs:
        rec_out = RecommendationOut(
            recommendation_id=r.recommendation_id,
            student_id=r.student_id,
            term=r.term,
            academic_year=r.academic_year,
            rule_code=r.rule_code,
            recommendation_text=r.recommendation_text,
            target_audience=r.target_audience,
            priority=r.priority,
            status=r.status,
            generated_at=r.generated_at,
            learning_path=lp_by_rec.get(r.recommendation_id),
        )
        formatted_recs.append(rec_out)

    return StudentAnalyticsOut(
        freshness=freshness.state if freshness else "stale",
        is_current=is_current,
        freshness_message=freshness.message if freshness else "Recalculate analytics to verify freshness.",
        analytics_id=analytics.analytics_id,
        student_id=analytics.student_id,
        term=analytics.term,
        academic_year=analytics.academic_year,
        overall_average=analytics.overall_average if is_current else None,
        support_probability=analytics.support_probability if is_current else None,
        support_status=analytics.support_status if is_current else "Recalculation needed",
        calculated_at=analytics.calculated_at,
        cohort_percentile=cohort_percentile if is_current else None,
        absences_count=absences_count,
        recommendations=formatted_recs if is_current else [],
        learning_path=[LearningPathItemOut.model_validate(lp) for lp in learning_paths] if is_current else [],
    )


@router.get(
    "/student/{student_id}/learning-path",
    response_model=List[LearningPathItemOut],
)
def get_learner_learning_path(
    student_id: int,
    term: Optional[str] = Query(None, description="Academic term; omit for all active"),
    academic_year: Optional[str] = Query(None, description="Academic year; omit for all active"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve tailored learning-path activities and educational resources for a learner.
    Enforces role-based permissions:
    - Admin: Full access.
    - Teacher: Authorized for students in assigned classes only.
    - Parent: Authorized for linked children only.
    """
    student = db.query(Student).filter(Student.student_id == student_id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with ID {student_id} not found.",
        )

    verify_student_access(current_user, student, db, allow_parent=True)

    items = LearningPathService.get_student_learning_path(
        db, student_id, term=term, academic_year=academic_year, active_only=True
    )
    fresh_periods = {(row.term, row.academic_year) for row in db.query(AnalyticsFreshness).filter_by(
        student_id=student_id, state="current").all()}
    return [LearningPathItemOut.model_validate(item) for item in items
            if (item.term, item.academic_year) in fresh_periods]


@router.get(
    "/learning-resources",
    response_model=List[LearningResourceOut],
)
def list_learning_resources(
    subject: Optional[str] = Query(None, description="Filter by subject or learning area"),
    grade_level: Optional[str] = Query(None, description="Filter by grade level"),
    alignment_type: Optional[str] = Query(None, description="Filter by CURRICULUM_ALIGNED or PROVISIONAL_SUPPORT"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List curated educational resources and activities from the starter catalogue.
    Available to all authenticated users (teachers, parents, administrators).
    """
    LearningPathService.seed_starter_catalogue_if_empty(db)
    query = db.query(LearningResource)
    if subject:
        query = query.filter(func.lower(LearningResource.subject_name) == subject.lower().strip())
    if grade_level:
        query = query.filter(LearningResource.grade_level == grade_level.strip())
    if alignment_type:
        query = query.filter(LearningResource.alignment_type == alignment_type.strip())

    resources = query.order_by(LearningResource.resource_id.asc()).all()
    return [LearningResourceOut.model_validate(r) for r in resources]
