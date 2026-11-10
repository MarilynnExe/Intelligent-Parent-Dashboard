"""Shared calculation pipeline and durable freshness tracking for teacher workflows."""
from datetime import datetime
import logging

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.academic_calendar import term_date_range
from app.models.academic import Assessment
from app.models.analytics import AnalyticsFreshness, StudentAnalytics
from app.models.behaviour import Attendance
from app.models.student import Student
from app.services.lifecycle_service import active_students
from app.services.catboost_service import ModelServiceError, get_catboost_service, map_period_absences_to_model_feature
from app.services.expert_system import ExpertSystemService
from app.services.percentile_service import PercentileService

logger = logging.getLogger(__name__)

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


def set_freshness(db, student_id, term, academic_year, state, message=None):
    row = db.query(AnalyticsFreshness).filter_by(
        student_id=student_id, term=term, academic_year=academic_year).first()
    if row is None:
        row = AnalyticsFreshness(student_id=student_id, term=term, academic_year=academic_year)
        db.add(row)
    row.state = state
    row.message = message
    row.updated_at = datetime.utcnow()
    db.flush()
    return row


def cohort_students(db, student):
    return db.query(Student).filter(active_students()).filter_by(grade_level=student.grade_level, stream=student.stream).all()


def invalidate(db, students, term, academic_year):
    # Called in the same transaction as teacher records, before their commit.
    for student in students:
        set_freshness(db, student.student_id, term, academic_year, "stale",
                      "Records changed. Analytics need recalculation.")


def refresh_students(db, students, term, academic_year):
    results = {}
    for student in students:
        student_id = student.student_id
        try:
            calculate(db, student, term, academic_year)
            results[student_id] = {"status": "current"}
        except Exception as exc:
            db.rollback()
            state = "pending" if isinstance(exc, HTTPException) and exc.status_code == 400 else "unavailable"
            message = (exc.detail if state == "pending"
                       else "Records saved. Analytics unavailable; ask the teacher to retry calculation.")
            set_freshness(db, student_id, term, academic_year, state, message)
            db.commit()
            logger.warning("Analytics refresh failed for student %s: %s", student_id, exc)
            results[student_id] = {"status": state, "message": message}
    return results


def calculate(db, student, term, academic_year):
    student_id = student.student_id
    term_date_range(term, academic_year)
    # Durable invalidation protects readers if any later calculation step fails.
    set_freshness(db, student_id, term, academic_year, "stale", "Calculation in progress; retry if it does not complete.")
    db.commit()
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
    try:
        catboost_service = get_catboost_service()
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

    set_freshness(db, student_id, term, academic_year, "current")
    db.commit()

    # 7. Dispatch Adaptive Notifications
    try:
        from app.services.notification_service import NotificationService
        NotificationService.dispatch_analytics_notifications(
            db=db,
            student=student,
            analytics=analytics,
            recommendations=recs,
            term=term,
            academic_year=academic_year,
            absences_count=absences_count,
            cohort_percentile=cohort_percentile,
        )
    except Exception as notif_err:
        db.rollback()
        logger.warning('Could not dispatch adaptive notifications: %s', notif_err)

    return analytics
