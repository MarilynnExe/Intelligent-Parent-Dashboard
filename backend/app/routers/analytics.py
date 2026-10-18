"""
Analytics and Risk Prediction Router.

Exposes endpoints for:
    - Calculating early-warning student academic risk via CatBoost ML-3 pipeline
    - Generating transparent pedagogical recommendations via the Expert System
    - Querying student risk status and analytics for teachers and parents
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.academic_calendar import term_date_range
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.models.academic import Assessment, CohortPercentile
from app.models.analytics import Recommendation, StudentAnalytics
from app.models.behaviour import Attendance
from app.models.student import ParentStudent, Student, TeacherAssignment
from app.models.user import User
from app.schemas.analytics import (
    CalculateAnalyticsRequest,
    RecommendationOut,
    StudentAnalyticsOut,
)
from app.services.catboost_service import (
    ModelServiceError,
    get_catboost_service,
    map_period_absences_to_model_feature,
)
from app.services.expert_system import ExpertSystemService
from app.services.percentile_service import PercentileService

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


def count_term_absences(db: Session, student_id: int, term: str, academic_year: str) -> int:
    """Count a student's absences recorded within the given term's date window."""
    try:
        start, end = term_date_range(term, academic_year)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return (
        db.query(func.count(Attendance.attendance_id))
        .filter(
            Attendance.student_id == student_id,
            Attendance.status == "Absent",
            Attendance.record_date >= start,
            Attendance.record_date <= end,
        )
        .scalar()
        or 0
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
    term = request.term if request else "Term 1"
    academic_year = request.academic_year if request else "2026"

    student = db.query(Student).filter(Student.student_id == student_id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with ID {student_id} not found.",
        )

    verify_student_access(current_user, student, db, allow_parent=False)

    # 1. Feature 1: first_term_pct (Period 1 assessments)
    assessments = (
        db.query(Assessment)
        .filter(
            Assessment.student_id == student_id,
            Assessment.term == term,
            Assessment.academic_year == academic_year,
        )
        .all()
    )

    if not assessments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"No assessment records found for student {student_id} in {term} {academic_year}. "
                "At least one Period 1 assessment is required to compute early-warning indicators."
            ),
        )

    overall_average = round(
        float(sum(a.percentage for a in assessments) / len(assessments)),
        2,
    )
    first_term_pct = overall_average

    # 2. Feature 2: cohort_percentile (Leak-free within cohort)
    cohort_percentile = PercentileService.get_or_calculate_student_percentile(
        db=db,
        student=student,
        term=term,
        academic_year=academic_year,
    )

    # 3. Feature 3: absences (this term only, mapped to benchmark scale)
    absences_count = count_term_absences(db, student_id, term, academic_year)

    mapped_absences = map_period_absences_to_model_feature(
        period_absences=absences_count,
        term_index=1,
        total_terms=3,
        annualize=True,
    )

    # 4. CatBoost + Platt Calibrator Prediction
    catboost_service = get_catboost_service()
    try:
        prediction = catboost_service.predict(
            first_term_pct=first_term_pct,
            cohort_percentile=cohort_percentile,
            absences=mapped_absences,
        )
    except ModelServiceError as exc:
        logger.error("CatBoost model service error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Academic risk prediction unavailable: {exc}",
        ) from exc

    support_probability = prediction["support_probability"]
    support_status = prediction["support_status"]

    # 5. Persist StudentAnalytics
    analytics = (
        db.query(StudentAnalytics)
        .filter(
            StudentAnalytics.student_id == student_id,
            StudentAnalytics.term == term,
            StudentAnalytics.academic_year == academic_year,
        )
        .first()
    )

    now = datetime.utcnow()
    if analytics:
        analytics.overall_average = overall_average
        analytics.support_probability = support_probability
        analytics.support_status = support_status
        analytics.calculated_at = now
    else:
        analytics = StudentAnalytics(
            student_id=student_id,
            term=term,
            academic_year=academic_year,
            overall_average=overall_average,
            support_probability=support_probability,
            support_status=support_status,
            calculated_at=now,
        )
        db.add(analytics)

    db.commit()
    db.refresh(analytics)

    # 6. Generate Expert System Recommendations
    recs = ExpertSystemService.evaluate_and_generate_recommendations(
        db=db,
        student=student,
        term=term,
        academic_year=academic_year,
        overall_average=overall_average,
        cohort_percentile=cohort_percentile,
        support_probability=support_probability,
        support_status=support_status,
        absences_count=absences_count,
    )

    return StudentAnalyticsOut(
        analytics_id=analytics.analytics_id,
        student_id=analytics.student_id,
        term=analytics.term,
        academic_year=analytics.academic_year,
        overall_average=analytics.overall_average,
        support_probability=analytics.support_probability,
        support_status=analytics.support_status,
        calculated_at=analytics.calculated_at,
        cohort_percentile=cohort_percentile,
        absences_count=absences_count,
        recommendations=[RecommendationOut.model_validate(r) for r in recs],
    )


@router.get(
    "/student/{student_id}",
    response_model=StudentAnalyticsOut,
)
def get_student_analytics(
    student_id: int,
    term: str = Query("Term 1", description="Academic term"),
    academic_year: str = Query("2026", description="Academic year"),
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

    analytics = (
        db.query(StudentAnalytics)
        .filter(
            StudentAnalytics.student_id == student_id,
            StudentAnalytics.term == term,
            StudentAnalytics.academic_year == academic_year,
        )
        .first()
    )

    if not analytics:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analytics not yet calculated for student {student_id} in {term} {academic_year}.",
        )

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

    return StudentAnalyticsOut(
        analytics_id=analytics.analytics_id,
        student_id=analytics.student_id,
        term=analytics.term,
        academic_year=analytics.academic_year,
        overall_average=analytics.overall_average,
        support_probability=analytics.support_probability,
        support_status=analytics.support_status,
        calculated_at=analytics.calculated_at,
        cohort_percentile=cohort_percentile,
        absences_count=absences_count,
        recommendations=[RecommendationOut.model_validate(r) for r in recs],
    )
