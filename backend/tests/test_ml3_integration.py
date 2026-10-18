"""
ML-3 Backend Integration Test Suite.

Verifies:
1. CatBoost model and Platt calibrator genuine artifact loading.
2. Exact feature ordering [first_term_pct, cohort_percentile, absences].
3. Platt calibration mapping and threshold-derived support status.
4. Fail-fast behavior with ModelServiceError on missing or corrupt model/calibrator (no fake fallback).
5. Transparent absence horizon mapping.
6. Leak-free cohort percentile calculation.
7. Expert system rule-based recommendation generation.
8. End-to-end analytics route execution and persistence in database.
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure backend directory is in sys.path
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.core.database import Base
from app.models.academic import Assessment, CohortPercentile
from app.models.analytics import Recommendation, StudentAnalytics
from app.models.behaviour import Attendance, BehaviourRecord
from app.models.student import ParentStudent, Student, TeacherAssignment
from app.models.user import User
from app.routers.analytics import calculate_student_analytics, get_student_analytics
from app.schemas.analytics import CalculateAnalyticsRequest
from app.services.catboost_service import (
    DEFAULT_CALIBRATOR_PATH,
    DEFAULT_MODEL_PATH,
    CatBoostService,
    ModelServiceError,
    determine_support_status,
    get_catboost_service,
    map_period_absences_to_model_feature,
)
from app.services.expert_system import ExpertSystemService
from app.services.percentile_service import PercentileService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def sqlite_engine():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def db_session(sqlite_engine):
    connection = sqlite_engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# ---------------------------------------------------------------------------
# 1. CatBoost Model & Calibrator Loading Tests
# ---------------------------------------------------------------------------

def test_catboost_service_loads_real_artifacts():
    """Verify that the CatBoostService loads genuine model and calibrator files."""
    assert DEFAULT_MODEL_PATH.exists(), f"Model file missing: {DEFAULT_MODEL_PATH}"
    assert DEFAULT_CALIBRATOR_PATH.exists(), f"Calibrator file missing: {DEFAULT_CALIBRATOR_PATH}"

    service = CatBoostService()
    assert service.model is not None
    assert service.calibrator is not None

    # Check calibrator attributes from ML-3 Platt scaling fit
    calibrator = service.calibrator
    assert hasattr(calibrator, "coef_")
    assert hasattr(calibrator, "intercept_")
    # Slope and intercept should match ML-3 training report (~6.0160, ~ -3.2113)
    assert abs(calibrator.coef_[0][0] - 6.0160) < 0.1
    assert abs(calibrator.intercept_[0] - (-3.2113)) < 0.1


def test_catboost_prediction_pipeline():
    """Verify prediction produces raw prob, calibrated prob, and correct status."""
    service = CatBoostService()

    # Mid-range student
    result = service.predict(first_term_pct=55.0, cohort_percentile=50.0, absences=4.0)
    assert "raw_probability" in result
    assert "support_probability" in result
    assert "support_status" in result
    assert "features" in result

    # Check range [0, 1]
    assert 0.0 <= result["raw_probability"] <= 1.0
    assert 0.0 <= result["support_probability"] <= 1.0

    # Check feature dict
    assert result["features"]["first_term_pct"] == 55.0
    assert result["features"]["cohort_percentile"] == 50.0
    assert result["features"]["absences"] == 4.0


def test_catboost_extreme_cases():
    """Verify high-performing learner is 'On Track' and struggling learner is 'Targeted Support'."""
    service = CatBoostService()

    # High performer: 95% first term, 98th percentile, 0 absences
    high_perf = service.predict(first_term_pct=95.0, cohort_percentile=98.0, absences=0.0)
    assert high_perf["support_probability"] < 0.35
    assert high_perf["support_status"] == "On Track"

    # Severely struggling learner: 20% first term, 5th percentile, 15 absences
    struggling = service.predict(first_term_pct=20.0, cohort_percentile=5.0, absences=15.0)
    assert struggling["support_probability"] >= 0.65
    assert struggling["support_status"] == "Targeted Support Recommended"


def test_missing_model_fails_loudly_without_fallback(tmp_path):
    """Verify that a missing model raises ModelServiceError and NEVER falls back."""
    fake_path = tmp_path / "nonexistent.cbm"
    with pytest.raises(ModelServiceError) as exc_info:
        CatBoostService(model_path=fake_path)
    assert "CatBoost model file not found" in str(exc_info.value)


def test_missing_calibrator_fails_loudly_without_fallback(tmp_path):
    """Verify that a missing calibrator raises ModelServiceError and NEVER falls back."""
    fake_cal_path = tmp_path / "nonexistent_cal.joblib"
    with pytest.raises(ModelServiceError) as exc_info:
        CatBoostService(calibrator_path=fake_cal_path)
    assert "Probability calibrator file not found" in str(exc_info.value)


def test_invalid_features_fail_fast():
    """Verify that non-numeric or missing features fail fast."""
    service = CatBoostService()
    with pytest.raises(ModelServiceError):
        service.predict(first_term_pct=None, cohort_percentile=50.0, absences=2.0)

    with pytest.raises(ModelServiceError):
        service.predict(first_term_pct="invalid", cohort_percentile=50.0, absences=2.0)


# ---------------------------------------------------------------------------
# 2. Absences Mapping Tests
# ---------------------------------------------------------------------------

def test_absences_mapping_annualized():
    """Verify transparent absences mapping to 3-term annual benchmark horizon."""
    # 2 absences in Term 1 (term 1 of 3) -> 2 * (3/1) = 6.0
    mapped = map_period_absences_to_model_feature(period_absences=2, term_index=1, total_terms=3, annualize=True)
    assert mapped == 6.0

    # 0 absences -> 0.0
    assert map_period_absences_to_model_feature(period_absences=0, annualize=True) == 0.0

    # Raw option without annualization
    raw = map_period_absences_to_model_feature(period_absences=4, annualize=False)
    assert raw == 4.0

    # Negative absences must raise ValueError
    with pytest.raises(ValueError):
        map_period_absences_to_model_feature(period_absences=-1)


# ---------------------------------------------------------------------------
# 3. PercentileService Tests
# ---------------------------------------------------------------------------

def test_percentile_service_overall_cohort(db_session):
    """Verify leak-free overall cohort percentile calculation on in-memory DB."""
    # Create 3 students in Grade 4, Stream East
    students = []
    for i, (adm, first, last) in enumerate([
        ("ADM001", "Alice", "Mwangi"),
        ("ADM002", "Bob", "Otieno"),
        ("ADM003", "Charlie", "Kamau"),
    ]):
        s = Student(
            admission_number=adm,
            first_name=first,
            last_name=last,
            date_of_birth=date(2015, 5, 10),
            gender="Female" if i == 0 else "Male",
            grade_level="Grade 4",
            stream="East",
        )
        db_session.add(s)
        students.append(s)
    db_session.commit()

    # Create dummy teacher for recorded_by_teacher_id
    teacher = User(
        full_name="Teacher One",
        email_or_username="teacher1@school.ke",
        password_hash="hash",
        role="TEACHER",
    )
    db_session.add(teacher)
    db_session.commit()

    # Scores: Alice=80%, Bob=60%, Charlie=40%
    scores = [80.0, 60.0, 40.0]
    for s, score in zip(students, scores):
        a = Assessment(
            student_id=s.student_id,
            subject_name="Mathematics",
            academic_year="2026",
            term="Term 1",
            assessment_type="Continuous Assessment",
            score=score,
            max_score=100.0,
            percentage=score,
            assessment_date=date(2026, 2, 1),
            recorded_by_teacher_id=teacher.user_id,
        )
        db_session.add(a)
    db_session.commit()

    # Calculate overall cohort percentiles
    recs = PercentileService.calculate_overall_cohort_percentiles(
        db=db_session,
        grade_level="Grade 4",
        stream="East",
        term="Term 1",
        academic_year="2026",
    )
    assert len(recs) == 3

    # Charlie (lowest: 0 below, 1 equal out of 3): (0 + 0.5)/3 * 100 = 16.7%
    charlie_pct = PercentileService.get_or_calculate_student_percentile(
        db_session, students[2], "Term 1", "2026"
    )
    assert abs(charlie_pct - 16.7) < 0.1

    # Bob (middle: 1 below, 1 equal out of 3): (1 + 0.5)/3 * 100 = 50.0%
    bob_pct = PercentileService.get_or_calculate_student_percentile(
        db_session, students[1], "Term 1", "2026"
    )
    assert abs(bob_pct - 50.0) < 0.1

    # Alice (highest: 2 below, 1 equal out of 3): (2 + 0.5)/3 * 100 = 83.3%
    alice_pct = PercentileService.get_or_calculate_student_percentile(
        db_session, students[0], "Term 1", "2026"
    )
    assert abs(alice_pct - 83.3) < 0.1

    # Charlie scores 100% in a new assessment: average 70% now ranks above Bob,
    # so the stored percentile must be refreshed rather than reused.
    db_session.add(Assessment(
        student_id=students[2].student_id,
        subject_name="Mathematics",
        academic_year="2026",
        term="Term 1",
        assessment_type="Exam",
        score=100.0,
        max_score=100.0,
        percentage=100.0,
        assessment_date=date(2026, 3, 1),
        recorded_by_teacher_id=teacher.user_id,
    ))
    db_session.commit()

    charlie_pct = PercentileService.get_or_calculate_student_percentile(
        db_session, students[2], "Term 1", "2026"
    )
    assert abs(charlie_pct - 50.0) < 0.1


# ---------------------------------------------------------------------------
# 4. Expert System Rules Tests
# ---------------------------------------------------------------------------

def test_expert_system_generates_rules(db_session):
    """Verify expert rules trigger appropriately based on support status, grades, and attendance."""
    student = Student(
        admission_number="ADM099",
        first_name="David",
        last_name="Ochieng",
        date_of_birth=date(2014, 3, 12),
        grade_level="Grade 5",
        stream="West",
    )
    db_session.add(student)
    db_session.commit()

    # Test High-Risk learner with excessive absences
    recs = ExpertSystemService.evaluate_and_generate_recommendations(
        db=db_session,
        student=student,
        term="Term 1",
        academic_year="2026",
        overall_average=42.0,
        cohort_percentile=15.0,
        support_probability=0.78,
        support_status="Targeted Support Recommended",
        absences_count=4,
    )

    rule_codes = {r.rule_code for r in recs}
    assert "ACAD_TARGETED_SUPPORT" in rule_codes
    assert "ATTEND_EXCESSIVE_ABSENCE" in rule_codes

    # Verify priorities
    targeted_rec = next(r for r in recs if r.rule_code == "ACAD_TARGETED_SUPPORT")
    assert targeted_rec.priority == "High"
    assert targeted_rec.target_audience == "Both"


# ---------------------------------------------------------------------------
# 5. End-to-End Analytics Route Execution Tests
# ---------------------------------------------------------------------------

def test_analytics_calculate_route_end_to_end(db_session):
    """Verify end-to-end analytics calculation endpoint produces genuine CatBoost output."""
    # 1. Create Teacher
    teacher = User(
        full_name="Madam Grace",
        email_or_username="grace@school.ke",
        password_hash="hashed_pw",
        role="TEACHER",
    )
    db_session.add(teacher)
    db_session.commit()

    # 2. Create Student
    student = Student(
        admission_number="ADM200",
        first_name="Faith",
        last_name="Wanjiku",
        date_of_birth=date(2015, 1, 15),
        gender="Female",
        grade_level="Grade 6",
        stream="North",
    )
    db_session.add(student)
    db_session.commit()

    # 3. Create Teacher Assignment
    assignment = TeacherAssignment(
        teacher_user_id=teacher.user_id,
        grade_level="Grade 6",
        stream="North",
        subject_name="Mathematics",
    )
    db_session.add(assignment)

    # 4. Create Period 1 Assessment
    assessment = Assessment(
        student_id=student.student_id,
        subject_name="Mathematics",
        academic_year="2026",
        term="Term 1",
        assessment_type="Beginning Term Assessment",
        score=72.0,
        max_score=100.0,
        percentage=72.0,
        assessment_date=date(2026, 1, 20),
        recorded_by_teacher_id=teacher.user_id,
    )
    db_session.add(assessment)

    # 5. Create 1 Attendance record (Absent)
    att = Attendance(
        student_id=student.student_id,
        record_date=date(2026, 1, 25),
        status="Absent",
        recorded_by_teacher_id=teacher.user_id,
    )
    db_session.add(att)
    db_session.commit()

    # 6. Execute calculate_student_analytics
    req = CalculateAnalyticsRequest(term="Term 1", academic_year="2026")
    result = calculate_student_analytics(
        student_id=student.student_id,
        request=req,
        current_user=teacher,
        db=db_session,
    )

    # Assertions
    assert result.student_id == student.student_id
    assert result.term == "Term 1"
    assert result.academic_year == "2026"
    assert result.overall_average == 72.0
    assert result.cohort_percentile is not None
    assert result.absences_count == 1

    # Check genuine CatBoost output
    assert result.support_probability is not None
    assert 0.0 <= result.support_probability <= 1.0
    assert result.support_status in ["On Track", "Monitoring Suggested", "Targeted Support Recommended"]

    # Verify database persistence
    stored = db_session.query(StudentAnalytics).filter(
        StudentAnalytics.student_id == student.student_id,
        StudentAnalytics.term == "Term 1",
        StudentAnalytics.academic_year == "2026",
    ).first()
    assert stored is not None
    assert stored.support_probability == result.support_probability
    assert stored.support_status == result.support_status
    assert stored.overall_average == 72.0

    # 7. Query endpoint retrieval
    query_result = get_student_analytics(
        student_id=student.student_id,
        term="Term 1",
        academic_year="2026",
        current_user=teacher,
        db=db_session,
    )
    assert query_result.analytics_id == result.analytics_id
    assert query_result.support_probability == result.support_probability


def test_absences_counted_only_within_term(db_session):
    """Absences from other terms or years must not feed the current term's analytics."""
    from app.routers.analytics import count_term_absences

    teacher = User(full_name="T", email_or_username="t-abs@school.ke", password_hash="x", role="TEACHER")
    student = Student(
        admission_number="ADM300", first_name="Joy", last_name="Akinyi",
        date_of_birth=date(2014, 6, 1), grade_level="Grade 7", stream="East",
    )
    db_session.add_all([teacher, student])
    db_session.commit()

    for day in (date(2026, 2, 3), date(2026, 4, 30), date(2026, 5, 4), date(2025, 2, 3)):
        db_session.add(Attendance(
            student_id=student.student_id, record_date=day,
            status="Absent", recorded_by_teacher_id=teacher.user_id,
        ))
    db_session.commit()

    assert count_term_absences(db_session, student.student_id, "Term 1", "2026") == 2
    assert count_term_absences(db_session, student.student_id, "Term 2", "2026") == 1
    assert count_term_absences(db_session, student.student_id, "Term 1", "2025") == 1
