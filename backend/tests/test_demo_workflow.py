"""Teacher-to-parent regression tests using real artifacts and isolated databases."""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.models.academic import Assessment, CohortPercentile
from app.models.analytics import StudentAnalytics
from app.models.behaviour import Attendance
from app.models.notification import Notification
from app.models.student import Student
from app.services.catboost_service import ModelServiceError
from scripts import seed_demo

PERIOD = {"term": "Term 3", "academic_year": "2026"}


@pytest.fixture
def demo(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'demo.db'}", connect_args={"check_same_thread": False})
    sessions = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(seed_demo, "engine", engine)
    monkeypatch.setattr(seed_demo, "SessionLocal", sessions)
    seed_demo.seed_demo("Term 3", "2026")
    def override_db():
        with sessions() as db:
            yield db
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        tokens = {}
        for role in ("admin", "teacher", "parent"):
            response = client.post("/api/auth/login", json={"email_or_username": f"demo.{role}", "password": seed_demo.DEMO_PASSWORD})
            assert response.status_code == 200
            tokens[role] = {"Authorization": "Bearer " + response.json()["access_token"]}
        with sessions() as db:
            students = {s.first_name: s.student_id for s in db.scalars(select(Student))}
        yield client, tokens, students, sessions
    app.dependency_overrides.clear()
    engine.dispose()


def analytics(client, tokens, student):
    return client.get(f"/api/analytics/student/{student}", params=PERIOD, headers=tokens["parent"])


def save_score(client, tokens, student, score=100):
    return client.post("/api/teacher/assessments", headers=tokens["teacher"], json={
        "student_id": student, "subject_name": "Mathematics", **PERIOD,
        "assessment_type": "CAT", "score": score, "max_score": 100, "assessment_date": "2026-09-20"})


def test_assessment_refreshes_cohort_and_parent_view(demo):
    client, tokens, students, sessions = demo
    before = analytics(client, tokens, students["Amina"]).json()
    with sessions() as db:
        peer_time = db.scalar(select(StudentAnalytics).filter_by(student_id=students["Brian"])).calculated_at
    result = save_score(client, tokens, students["Amina"])
    assert result.status_code == 200
    after = analytics(client, tokens, students["Amina"]).json()
    assert after["is_current"] is True
    assert after["overall_average"] > before["overall_average"]
    assert after["support_probability"] != before["support_probability"]
    assert after["recommendations"]
    with sessions() as db:
        assert db.scalar(select(StudentAnalytics).filter_by(student_id=students["Brian"])).calculated_at > peer_time
        rank = db.scalar(select(CohortPercentile).filter_by(student_id=students["Amina"], subject_name=None))
        assert rank.percentile_rank == after["cohort_percentile"]


def test_model_failure_keeps_record_and_hides_old_prediction_then_retry(demo, monkeypatch):
    client, tokens, students, sessions = demo
    from app.services import analytics_service
    original = analytics_service.get_catboost_service
    def broken():
        raise ModelServiceError("simulated artifact failure")
    monkeypatch.setattr(analytics_service, "get_catboost_service", broken)
    response = save_score(client, tokens, students["Amina"])
    assert response.status_code == 200
    assert response.json()["analytics_refresh"]["status"] == "incomplete"
    stale = analytics(client, tokens, students["Amina"]).json()
    assert stale["freshness"] == "unavailable"
    assert stale["support_probability"] is None
    assert stale["overall_average"] is None
    assert stale["recommendations"] == []
    assert client.get(f"/api/analytics/student/{students['Amina']}/learning-path", params=PERIOD,
                      headers=tokens["parent"]).json() == []
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Assessment).filter_by(student_id=students["Amina"])) == 5
    progress = client.get(f"/api/parent/children/{students['Amina']}/progress", params=PERIOD, headers=tokens["parent"]).json()
    assert progress["overall_average"] == 48
    assert progress["freshness"] == "unavailable"
    monkeypatch.setattr(analytics_service, "get_catboost_service", original)
    retry = client.post(f"/api/analytics/calculate/{students['Amina']}", json=PERIOD, headers=tokens["teacher"])
    assert retry.status_code == 200
    assert retry.json()["is_current"] is True
    # Retrying refreshes the other affected learners as well.
    with sessions() as db:
        assert db.scalar(select(StudentAnalytics).filter_by(student_id=students["Brian"])).support_probability is not None


def test_attendance_correction_and_behaviour_are_period_scoped(demo):
    client, tokens, students, sessions = demo
    student = students["Amina"]
    response = client.post("/api/teacher/attendance/bulk", headers=tokens["teacher"], json={
        "record_date": "2026-09-06", "entries": [{"student_id": student, "status": "Present"}]})
    assert response.status_code == 200
    assert response.json()["analytics_refresh"][str(student)]["status"] == "current"
    assert analytics(client, tokens, student).json()["absences_count"] == 2
    record = client.post("/api/teacher/behaviour", headers=tokens["teacher"], json={
        "student_id": students["Brian"], "record_date": "2026-02-02", "category": "Engagement", "rating": 1})
    assert record.status_code == 200
    recalc = client.post(f"/api/analytics/calculate/{students['Brian']}", json=PERIOD, headers=tokens["teacher"])
    assert "BEHAV_ATTENTION_REQUIRED" not in {r["rule_code"] for r in recalc.json()["recommendations"]}
    current = client.post("/api/teacher/behaviour", headers=tokens["teacher"], json={
        "student_id": student, "record_date": "2026-09-21", "category": "Cooperation", "rating": 1})
    assert current.json()["analytics_refresh"][str(student)]["status"] == "current"
    assert "BEHAV_ATTENTION_REQUIRED" in {r["rule_code"] for r in analytics(client, tokens, student).json()["recommendations"]}
    notifications = client.get("/api/notifications", headers=tokens["parent"]).json()
    assert any(n["category"] == "BEHAVIOUR" for n in notifications)


def test_progress_empty_period_and_authorization(demo):
    client, tokens, students, sessions = demo
    url = f"/api/parent/children/{students['Amina']}/progress"
    response = client.get(url, params=PERIOD, headers=tokens["parent"])
    assert response.status_code == 200
    data = response.json()
    assert len(data["assessments"]) == 4
    assert data["attendance_totals"] == {"Present": 3, "Absent": 3, "Late": 0, "Excused": 0, "recorded": 6}
    assert data["attendance_months"][0]["absent"] == 3
    empty = client.get(url, params={"term": "Term 1", "academic_year": "2025"}, headers=tokens["parent"]).json()
    assert empty["assessments"] == [] and empty["attendance_totals"]["recorded"] == 0
    assert empty["freshness"] == "pending"
    assert client.get(url, params={"term": "Term 4"}, headers=tokens["parent"]).status_code == 400
    assert client.get(f"/api/parent/children/{students['Brian']}/progress", params=PERIOD, headers=tokens["parent"]).status_code == 403
    assert save_score(client, tokens, students["Esther"]).status_code == 403
    assert client.post(f"/api/analytics/calculate/{students['Amina']}", json=PERIOD, headers=tokens["parent"]).status_code == 403
    missing = client.get(f"/api/parent/children/{students['David']}/progress", params=PERIOD, headers=tokens["parent"]).json()
    assert missing["freshness"] == "pending"


def test_repeatable_demo_and_notifications_do_not_duplicate(demo):
    client, tokens, students, sessions = demo
    def counts():
        with sessions() as db:
            return tuple(db.scalar(select(func.count()).select_from(model)) for model in (Student, Assessment, Attendance, Notification))
    before = counts()
    seed_demo.seed_demo("Term 3", "2026")
    assert counts() == before
    for _ in range(2):
        assert client.post(f"/api/analytics/calculate/{students['Amina']}", json=PERIOD, headers=tokens["teacher"]).status_code == 200
    assert counts() == before


def test_frontend_assets_are_served_with_correct_case(demo):
    client, _, _, _ = demo
    page = client.get("/portal/parent-dashboard.html")
    assert page.status_code == 200 and 'src="JS/parent-dashboard.js"' in page.text
    for asset in ("JS/api.js", "JS/parent-dashboard.js", "JS/teacher-dashboard.js", "css/parent-dashboard.css"):
        assert client.get(f"/portal/{asset}").status_code == 200


def test_first_prediction_failure_has_unavailable_state_without_losing_score(demo, monkeypatch):
    client, tokens, students, sessions = demo
    from app.services import analytics_service
    def broken():
        raise ModelServiceError("simulated missing model")
    monkeypatch.setattr(analytics_service, "get_catboost_service", broken)
    response = save_score(client, tokens, students["David"], score=70)
    assert response.status_code == 200
    assert analytics(client, tokens, students["David"]).status_code == 404
    data = client.get(f"/api/parent/children/{students['David']}/progress", params=PERIOD, headers=tokens["parent"]).json()
    assert data["freshness"] == "unavailable"
    assert data["overall_average"] == 70 and len(data["assessments"]) == 1


def test_notification_read_cooldown_uses_read_time(demo):
    client, tokens, students, sessions = demo
    from datetime import datetime, timedelta
    from app.services.notification_service import NotificationService
    with sessions() as db:
        notification = db.scalar(select(Notification).filter_by(student_id=students["Amina"], category="BEHAVIOUR"))
        notification.created_at = datetime.utcnow() - timedelta(days=3)
        notification.is_read = True
        notification.read_at = datetime.utcnow()
        db.commit()
        count = db.scalar(select(func.count()).select_from(Notification))
        result = NotificationService.send_notification(db, notification.recipient_user_id, "BEHAVIOUR", "MEDIUM",
            "Classroom guidance", "Detailed", dedup_key=notification.dedup_key)
        assert result.notification_id == notification.notification_id
        assert db.scalar(select(func.count()).select_from(Notification)) == count


def test_learning_path_reason_fits_mysql_limit(demo):
    _, _, _, sessions = demo
    from app.models.learning_path import LearningPathItem
    with sessions() as db:
        items = list(db.scalars(select(LearningPathItem)))
        assert items
        assert all(len(item.reason) <= 500 for item in items)
