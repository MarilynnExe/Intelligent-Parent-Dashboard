"""
Unit and Integration Tests for Adaptive Notifications and Preferences.
"""

from __future__ import annotations

from datetime import date
import pytest
from fastapi.testclient import TestClient

from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.main import app
from app.models.academic import Assessment
from app.models.behaviour import Attendance
from app.models.notification import Notification, NotificationPreference
from app.models.student import ParentStudent, Student, TeacherAssignment
from app.models.user import User

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
        ("Grade 7 Teacher", "teacher7", "TEACHER"),
        ("Other Teacher", "other_teacher", "TEACHER"),
        ("Parent One", "parent1", "PARENT"),
        ("Parent Two", "parent2", "PARENT"),
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

    # Create students
    s1 = Student(
        admission_number="ADM-001",
        first_name="Brian",
        last_name="Otieno",
        date_of_birth=date(2012, 5, 10),
        gender="Male",
        grade_level="Grade 7",
        stream="East",
    )
    s2 = Student(
        admission_number="ADM-002",
        first_name="Faith",
        last_name="Wanjiku",
        date_of_birth=date(2012, 8, 15),
        gender="Female",
        grade_level="Grade 7",
        stream="West",
    )
    db.add(s1)
    db.add(s2)
    db.commit()

    # Parent 1 -> Student 1 (Brian)
    db.add(ParentStudent(parent_user_id=user_objs["parent1"].user_id, student_id=s1.student_id, relationship_type="Father"))
    # Parent 2 -> Student 2 (Faith)
    db.add(ParentStudent(parent_user_id=user_objs["parent2"].user_id, student_id=s2.student_id, relationship_type="Mother"))

    # Teacher 7 -> Grade 7 East (Brian's class)
    db.add(TeacherAssignment(teacher_user_id=user_objs["teacher7"].user_id, grade_level="Grade 7", stream="East", subject_name="Mathematics"))
    # Other Teacher -> Grade 8 North
    db.add(TeacherAssignment(teacher_user_id=user_objs["other_teacher"].user_id, grade_level="Grade 8", stream="North", subject_name="Science"))

    # Add assessments for Brian in Term 1 2026 (failing so high risk support recommended)
    for subj, score in [("Mathematics", 35.0), ("English", 40.0), ("Science", 38.0)]:
        db.add(Assessment(
            student_id=s1.student_id,
            subject_name=subj,
            academic_year="2026",
            term="Term 1",
            assessment_type="Continuous Assessment",
            score=score,
            max_score=100.0,
            percentage=score,
            assessment_date=date(2026, 2, 15),
            recorded_by_teacher_id=user_objs["teacher7"].user_id,
        ))

    # Add 4 absences for Brian
    for day in range(1, 5):
        db.add(Attendance(
            student_id=s1.student_id,
            record_date=date(2026, 2, day),
            status="Absent",
            remarks="Unexcused",
            recorded_by_teacher_id=user_objs["teacher7"].user_id,
        ))

    db.commit()
    db.close()

    return TestClient(app)


def login(client, username):
    return client.post("/api/auth/login", json={"email_or_username": username, "password": PASSWORD})


@pytest.fixture(scope="module")
def tokens(client):
    users = ["admin", "teacher7", "other_teacher", "parent1", "parent2"]
    return {u: login(client, u).json()["access_token"] for u in users}


def test_notifications_unauthenticated(client):
    res = client.get("/api/notifications")
    assert res.status_code == 401


def test_notifications_empty_initially(client, tokens):
    res = client.get("/api/notifications", headers=auth(tokens["parent1"]))
    assert res.status_code == 200
    assert res.json() == []

    count_res = client.get("/api/notifications/unread-count", headers=auth(tokens["parent1"]))
    assert count_res.status_code == 200
    assert count_res.json()["unread_count"] == 0


def test_preferences_get_and_update(client, tokens):
    res = client.get("/api/notifications/preferences", headers=auth(tokens["parent1"]))
    assert res.status_code == 200
    data = res.json()
    assert data["notifications_enabled"] is True
    assert data["communication_style"] == "DETAILED"

    # Update preference to CONCISE and disable behaviour
    update_res = client.put(
        "/api/notifications/preferences",
        headers=auth(tokens["parent1"]),
        json={"communication_style": "CONCISE", "behaviour_updates": False},
    )
    assert update_res.status_code == 200
    updated_data = update_res.json()
    assert updated_data["communication_style"] == "CONCISE"
    assert updated_data["behaviour_updates"] is False


def test_analytics_calculation_generates_notifications(client, tokens):
    # Teacher calculates analytics for Brian (student_id = 1)
    calc_res = client.post(
        "/api/analytics/calculate/1",
        headers=auth(tokens["teacher7"]),
        json={"term": "Term 1", "academic_year": "2026"},
    )
    assert calc_res.status_code == 200, calc_res.text

    # Parent 1 should have notifications about Brian (Targeted Support + Attendance)
    p1_res = client.get("/api/notifications", headers=auth(tokens["parent1"]))
    assert p1_res.status_code == 200
    p1_notifs = p1_res.json()
    assert len(p1_notifs) >= 1

    # Check content of the top notification
    top = p1_notifs[0]
    assert "Brian" in top["title"] or "Brian" in top["message"]
    assert top["priority"] in ["HIGH", "MEDIUM", "LOW"]
    assert top["student_id"] == 1
    assert top["student_name"] == "Brian Otieno"
    assert top["suggested_action"] is not None

    # Teacher 7 (assigned to Brian's class) should also have a notification
    t7_res = client.get("/api/notifications", headers=auth(tokens["teacher7"]))
    assert t7_res.status_code == 200
    t7_notifs = t7_res.json()
    assert len(t7_notifs) >= 1

    # Other Teacher (Grade 8) should NOT receive notifications for Brian
    other_t_res = client.get("/api/notifications", headers=auth(tokens["other_teacher"]))
    assert other_t_res.status_code == 200
    assert len(other_t_res.json()) == 0

    # Parent 2 (linked to Faith, not Brian) should NOT see Brian's notifications
    p2_res = client.get("/api/notifications", headers=auth(tokens["parent2"]))
    assert p2_res.status_code == 200
    assert len(p2_res.json()) == 0


def test_mark_notification_as_read(client, tokens):
    p1_res = client.get("/api/notifications?unread_only=true", headers=auth(tokens["parent1"]))
    notifs = p1_res.json()
    assert len(notifs) > 0
    notif_id = notifs[0]["notification_id"]

    # Mark as read
    read_res = client.patch(f"/api/notifications/{notif_id}/read", headers=auth(tokens["parent1"]))
    assert read_res.status_code == 200
    assert read_res.json()["is_read"] is True
    assert read_res.json()["read_at"] is not None

    # Check unread count decreased
    count_res = client.get("/api/notifications/unread-count", headers=auth(tokens["parent1"]))
    assert count_res.json()["unread_count"] == len(notifs) - 1


def test_user_cannot_mark_other_users_notification(client, tokens):
    p1_res = client.get("/api/notifications", headers=auth(tokens["parent1"]))
    notif_id = p1_res.json()[0]["notification_id"]

    # Parent 2 attempts to mark Parent 1's notification as read
    hack_res = client.patch(f"/api/notifications/{notif_id}/read", headers=auth(tokens["parent2"]))
    assert hack_res.status_code in [403, 404]


def test_mark_all_read(client, tokens):
    mark_all_res = client.patch("/api/notifications/mark-all-read", headers=auth(tokens["parent1"]))
    assert mark_all_res.status_code == 200

    count_res = client.get("/api/notifications/unread-count", headers=auth(tokens["parent1"]))
    assert count_res.json()["unread_count"] == 0


def test_analytics_deduplication(client, tokens):
    # Record current count of notifications for Parent 1
    p1_initial = client.get("/api/notifications", headers=auth(tokens["parent1"])).json()
    initial_count = len(p1_initial)

    # Re-calculate analytics again immediately
    re_calc = client.post(
        "/api/analytics/calculate/1",
        headers=auth(tokens["teacher7"]),
        json={"term": "Term 1", "academic_year": "2026"},
    )
    assert re_calc.status_code == 200

    # Ensure no duplicate rows were spammed
    p1_after = client.get("/api/notifications", headers=auth(tokens["parent1"])).json()
    assert len(p1_after) == initial_count


def test_high_priority_bypasses_category_disable(client, tokens):
    # Disable all updates for parent 1
    client.put(
        "/api/notifications/preferences",
        headers=auth(tokens["parent1"]),
        json={"notifications_enabled": False, "support_updates": False},
    )

    # Directly dispatch high priority notification using the service
    from app.services.notification_service import NotificationService
    db = SessionLocal()
    notif = NotificationService.send_notification(
        db=db,
        recipient_user_id=4,  # parent1
        student_id=1,
        category="SUPPORT",
        priority="HIGH",
        title="Urgent Learning Support Advisory",
        message_detailed="This high-priority advisory must be delivered despite toggles.",
        suggested_action="Contact school immediately.",
        dedup_key="test:high_priority_bypass_unique",
    )
    db.close()
    assert notif is not None
    assert notif.priority == "HIGH"

    # Confirm it appears in parent 1's notification list
    p1_notifs = client.get("/api/notifications", headers=auth(tokens["parent1"])).json()
    found = any(n["title"] == "Urgent Learning Support Advisory" for n in p1_notifs)
    assert found is True
