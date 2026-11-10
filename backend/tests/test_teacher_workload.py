"""
Automated Tests for Teacher Workload Monitoring and Balancing Module.
"""

from __future__ import annotations

from datetime import date, datetime
import pytest
from fastapi.testclient import TestClient

from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.main import app
from app.models.academic import Assessment
from app.models.analytics import StudentAnalytics
from app.models.behaviour import Attendance
from app.models.notification import Notification
from app.models.student import Student, TeacherAssignment
from app.models.user import User
from app.services.workload_service import (
    WEIGHT_CLASS,
    WEIGHT_LEARNER,
    WEIGHT_MONITORING,
    WEIGHT_SUBJECT_PREPARATION,
    WEIGHT_TARGETED_SUPPORT,
    WorkloadService,
)

PASSWORD = "pass1234"


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    # Create users
    users = [
        ("System Administrator", "admin", "ADMIN"),
        ("Madam Grace (Lead Teacher)", "grace", "TEACHER"),
        ("Mr. Kipchoge (Science Teacher)", "kipchoge", "TEACHER"),
        ("Ms. Auma (Unassigned Teacher)", "auma", "TEACHER"),
        ("Parent One", "parent1", "PARENT"),
    ]
    user_objs = {}
    for name, username, role in users:
        u = User(
            full_name=name,
            email_or_username=username,
            password_hash=hash_password(PASSWORD),
            role=role,
        )
        db.add(u)
        user_objs[username] = u
    db.commit()

    # Create students:
    # Class 1: Grade 7 East (3 students)
    # Class 2: Grade 7 West (2 students)
    # Class 3: Grade 8 North (1 student)
    students = [
        # Grade 7 East
        ("ADM-WL-001", "Kevin", "Ochieng", "Grade 7", "East"),
        ("ADM-WL-002", "Faith", "Wanjiku", "Grade 7", "East"),
        ("ADM-WL-003", "Brian", "Kariuki", "Grade 7", "East"),
        # Grade 7 West
        ("ADM-WL-004", "Mercy", "Chebet", "Grade 7", "West"),
        ("ADM-WL-005", "Dennis", "Mutua", "Grade 7", "West"),
        # Grade 8 North
        ("ADM-WL-006", "Zawadi", "Otieno", "Grade 8", "North"),
    ]
    student_objs = {}
    for adm, fn, ln, gl, st in students:
        s = Student(
            admission_number=adm,
            first_name=fn,
            last_name=ln,
            date_of_birth=date(2012, 1, 1),
            grade_level=gl,
            stream=st,
        )
        db.add(s)
        student_objs[adm] = s
    db.commit()

    # Setup Teacher Assignments:
    # 1. Madam Grace -> Grade 7 East (Math & English) + Grade 7 West (Math)
    # Total distinct classes = 2 (Grade 7 East, Grade 7 West)
    # Total subject preparations = 3 (East Math, East English, West Math) - tests multiple subjects in one class!
    # Total learners in those classes = 3 (East) + 2 (West) = 5 learners
    db.add(TeacherAssignment(teacher_user_id=user_objs["grace"].user_id, grade_level="Grade 7", stream="East", subject_name="Mathematics"))
    db.add(TeacherAssignment(teacher_user_id=user_objs["grace"].user_id, grade_level="Grade 7", stream="East", subject_name="English"))
    db.add(TeacherAssignment(teacher_user_id=user_objs["grace"].user_id, grade_level="Grade 7", stream="West", subject_name="Mathematics"))

    # 2. Mr. Kipchoge -> Grade 8 North (Science)
    # Total distinct classes = 1 (Grade 8 North)
    # Total subject preparations = 1
    # Total learners = 1 (Zawadi)
    db.add(TeacherAssignment(teacher_user_id=user_objs["kipchoge"].user_id, grade_level="Grade 8", stream="North", subject_name="Science"))

    # 3. Ms. Auma -> No assignments (Unassigned / Available Capacity)

    db.commit()

    # Setup StudentAnalytics for learners in Madam Grace's classes:
    # Kevin -> "Targeted Support Recommended"
    db.add(StudentAnalytics(
        student_id=student_objs["ADM-WL-001"].student_id,
        term="Term 1",
        academic_year="2026",
        overall_average=42.0,
        support_probability=0.82,
        support_status="Targeted Support Recommended",
        calculated_at=datetime.utcnow(),
    ))
    # Faith -> "Monitoring Suggested"
    db.add(StudentAnalytics(
        student_id=student_objs["ADM-WL-002"].student_id,
        term="Term 1",
        academic_year="2026",
        overall_average=58.0,
        support_probability=0.45,
        support_status="Monitoring Suggested",
        calculated_at=datetime.utcnow(),
    ))
    # Brian -> "On Track"
    db.add(StudentAnalytics(
        student_id=student_objs["ADM-WL-003"].student_id,
        term="Term 1",
        academic_year="2026",
        overall_average=78.0,
        support_probability=0.12,
        support_status="On Track",
        calculated_at=datetime.utcnow(),
    ))
    # Mercy -> No analytics yet (unassessed)
    # Dennis -> "On Track"
    db.add(StudentAnalytics(
        student_id=student_objs["ADM-WL-005"].student_id,
        term="Term 1",
        academic_year="2026",
        overall_average=81.0,
        support_probability=0.08,
        support_status="On Track",
        calculated_at=datetime.utcnow(),
    ))

    # Add unread notifications for Madam Grace (1 High priority, 1 Medium)
    db.add(Notification(
        recipient_user_id=user_objs["grace"].user_id,
        category="ACADEMIC_INTERVENTION",
        priority="High",
        title="High Academic Risk Alert",
        message="Kevin Ochieng requires targeted support.",
        is_read=False,
    ))
    db.add(Notification(
        recipient_user_id=user_objs["grace"].user_id,
        category="SYSTEM",
        priority="Medium",
        title="Term Calendar Published",
        message="Please review term assessment dates.",
        is_read=False,
    ))

    db.commit()
    db.close()

    return TestClient(app)


def login(client, username):
    return client.post("/api/auth/login", json={"email_or_username": username, "password": PASSWORD})


@pytest.fixture(scope="module")
def tokens(client):
    users = ["admin", "grace", "kipchoge", "auma", "parent1"]
    return {u: login(client, u).json()["access_token"] for u in users}


# ---------------------------------------------------------------------------
# Access Control Tests (RBAC)
# ---------------------------------------------------------------------------

def test_admin_can_access_workload_endpoint(client, tokens):
    res = client.get("/api/admin/teacher-workload", headers=auth(tokens["admin"]))
    assert res.status_code == 200
    data = res.json()
    assert "summary" in data
    assert "teachers" in data
    assert "balancing_recommendations" in data
    assert "scoring_methodology" in data


def test_teacher_forbidden_from_overall_workload_endpoint(client, tokens):
    # Teachers must NOT access other teachers' workload records
    res = client.get("/api/admin/teacher-workload", headers=auth(tokens["grace"]))
    assert res.status_code == 403
    assert "permission" in res.json()["detail"].lower()


def test_parent_forbidden_from_workload_endpoint(client, tokens):
    # Parents must NOT access administrative workload records
    res = client.get("/api/admin/teacher-workload", headers=auth(tokens["parent1"]))
    assert res.status_code == 403


def test_unauthenticated_rejected_from_workload_endpoint(client):
    # Unauthenticated requests must be rejected with 401
    res = client.get("/api/admin/teacher-workload")
    assert res.status_code == 401


def test_teacher_forbidden_from_single_teacher_workload(client, tokens):
    # Even single teacher endpoint must be restricted to ADMIN
    res = client.get("/api/admin/teacher-workload/2", headers=auth(tokens["grace"]))
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# Functional Calculation Tests
# ---------------------------------------------------------------------------

def test_unassigned_teacher_workload_metrics(client, tokens):
    res = client.get("/api/admin/teacher-workload", headers=auth(tokens["admin"]))
    assert res.status_code == 200
    data = res.json()

    auma = next((t for t in data["teachers"] if "auma" in t["email_or_username"].lower()), None)
    assert auma is not None, "Ms. Auma must be in teacher workload report"

    assert auma["total_classes_count"] == 0
    assert auma["assigned_classes"] == []
    assert auma["subject_assignments_count"] == 0
    assert auma["assigned_learners_count"] == 0
    assert auma["targeted_support_count"] == 0
    assert auma["monitoring_count"] == 0
    assert auma["on_track_count"] == 0
    assert auma["workload_score"] == 0.0
    assert auma["workload_status"] == "UNASSIGNED"
    assert auma["workload_label"] == "No Active Assignments"
    assert "no assigned streams or classes" in auma["explanation"].lower()


def test_assigned_teacher_workload_metrics_and_multi_subject(client, tokens):
    """
    Verifies that:
    - Multiple subjects in the same class (Math + English in Grade 7 East) are correctly
      distinguished: total_classes_count = 2, subject_assignments_count = 3.
    - The refined formula correctly weighs class cohorts and subject preparations.
    """
    res = client.get("/api/admin/teacher-workload", headers=auth(tokens["admin"]))
    assert res.status_code == 200
    data = res.json()

    grace = next((t for t in data["teachers"] if "grace" in t["email_or_username"].lower()), None)
    assert grace is not None

    # Classes: Grade 7 East, Grade 7 West (2 distinct class cohorts)
    assert grace["total_classes_count"] == 2
    assert "Grade 7 East" in grace["assigned_classes"]
    assert "Grade 7 West" in grace["assigned_classes"]

    # Subject-class preparations: 3 (Math in East, English in East, Math in West)
    assert grace["subject_assignments_count"] == 3
    assert set(grace["assigned_subjects"]) == {"Mathematics", "English"}

    # Learners in Grade 7 East (3) + Grade 7 West (2) = 5 learners
    assert grace["assigned_learners_count"] == 5

    # Learner support distribution:
    # 1 Targeted (Kevin), 1 Monitoring (Faith), 2 On Track (Brian, Dennis), 1 Unassessed (Mercy)
    assert grace["targeted_support_count"] == 1
    assert grace["monitoring_count"] == 1
    assert grace["on_track_count"] == 2
    assert grace["unassessed_learners_count"] == 1

    # Notifications: 2 unread, 1 high priority
    assert grace["unread_notifications_count"] == 2
    assert grace["high_priority_notifications_count"] == 1

    # Refined formula check:
    # Score = (5 * 1.0) + (2 * 3.0) + (3 * 2.0) + (1 * 3.0) + (1 * 1.5) = 5 + 6 + 6 + 3 + 1.5 = 21.5
    expected_score = (
        (5 * WEIGHT_LEARNER)
        + (2 * WEIGHT_CLASS)
        + (3 * WEIGHT_SUBJECT_PREPARATION)
        + (1 * WEIGHT_TARGETED_SUPPORT)
        + (1 * WEIGHT_MONITORING)
    )
    assert abs(grace["workload_score"] - expected_score) < 0.01

    # Status check:
    # Score 21.5 < 30.0 -> "LOW" / "Available Capacity"
    assert grace["workload_status"] == "LOW"
    assert grace["workload_label"] == "Available Capacity"
    assert "21.5" in grace["explanation"]


def test_notifications_do_not_alter_workload_score(client, tokens):
    """
    Verifies that notifications are strictly supplementary operational indicators
    and do NOT artificially alter the workload score.
    """
    # 1. Fetch initial score for Madam Grace
    res1 = client.get("/api/admin/teacher-workload", headers=auth(tokens["admin"]))
    grace1 = next(t for t in res1.json()["teachers"] if "grace" in t["email_or_username"])
    initial_score = grace1["workload_score"]
    initial_unreads = grace1["unread_notifications_count"]

    # 2. Add 5 more high-priority notifications for Madam Grace
    db = SessionLocal()
    try:
        grace_user = db.query(User).filter(User.email_or_username == "grace").first()
        for i in range(5):
            db.add(Notification(
                recipient_user_id=grace_user.user_id,
                category="ACADEMIC_INTERVENTION",
                priority="High",
                title=f"Urgent Notice {i}",
                message="Review required.",
                is_read=False,
            ))
        db.commit()
    finally:
        db.close()

    # 3. Fetch updated workload report
    res2 = client.get("/api/admin/teacher-workload", headers=auth(tokens["admin"]))
    grace2 = next(t for t in res2.json()["teachers"] if "grace" in t["email_or_username"])

    # Unread notifications must update
    assert grace2["unread_notifications_count"] == initial_unreads + 5
    assert grace2["high_priority_notifications_count"] >= 5

    # But workload score MUST remain identical!
    assert grace2["workload_score"] == initial_score, "Notifications must NOT affect the workload score!"


def test_single_teacher_workload_endpoint(client, tokens):
    all_res = client.get("/api/admin/teacher-workload", headers=auth(tokens["admin"]))
    grace_summary = next(t for t in all_res.json()["teachers"] if "grace" in t["email_or_username"])
    teacher_id = grace_summary["teacher_user_id"]

    single_res = client.get(f"/api/admin/teacher-workload/{teacher_id}", headers=auth(tokens["admin"]))
    assert single_res.status_code == 200
    item = single_res.json()
    assert item["teacher_user_id"] == teacher_id
    assert item["teacher_name"] == grace_summary["teacher_name"]
    assert item["workload_score"] == grace_summary["workload_score"]

    # Non-existent teacher ID -> 404
    not_found = client.get("/api/admin/teacher-workload/9999", headers=auth(tokens["admin"]))
    assert not_found.status_code == 404


def test_workload_summary_and_subject_aware_balancing_recommendations(client, tokens):
    """
    Verifies that balancing recommendations:
    - Identify teachers with available capacity.
    - Avoid claiming unverified subject competence when qualifications are not in the database.
    - Frame suggestions as advisory items requiring administrator review.
    """
    res = client.get("/api/admin/teacher-workload", headers=auth(tokens["admin"]))
    assert res.status_code == 200
    data = res.json()

    summary = data["summary"]
    assert summary["total_teachers"] == 3  # Grace, Kipchoge, Auma
    assert summary["active_teachers_count"] == 2  # Grace, Kipchoge
    assert summary["unassigned_teachers_count"] == 1  # Auma
    assert summary["total_targeted_support_learners"] == 1
    assert summary["total_learners_monitored"] == 1

    # Check recommendations: Ms. Auma is unassigned, so a CAPACITY_AVAILABLE recommendation must exist
    recs = data["balancing_recommendations"]
    assert len(recs) >= 1

    capacity_rec = next((r for r in recs if r["recommendation_type"] == "CAPACITY_AVAILABLE"), None)
    assert capacity_rec is not None
    assert "Auma" in capacity_rec["message"]
    assert "administrator review" in capacity_rec["message"].lower()

    # Methodology disclaimer must be present and state it is an administrative operational heuristic
    methodology = data["scoring_methodology"]
    assert "heuristic" in methodology.lower()
    assert "not a clinically or scientifically validated measure" in methodology.lower()
    assert "not in the score" in methodology.lower() or "do not factor into the score" in methodology.lower()
