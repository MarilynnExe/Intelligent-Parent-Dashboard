"""CRUD audit; optional MySQL target must be a disposable *_crud_test database."""
import os
import re
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from app.core.database import Base, get_db
from app.main import app
from app.models.behaviour import Attendance
from app.models.student import Student
from app.models.user import User
from app.services.notification_service import NotificationService
from scripts import seed_demo

PERIOD = {"term": "Term 3", "academic_year": "2026"}

@pytest.fixture
def audit(tmp_path, monkeypatch):
    url = os.getenv("CRUD_TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'audit.db'}")
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite" and not (parsed.database or "").endswith("_crud_test"):
        pytest.fail("Use a disposable *_crud_test database")
    engine = create_engine(url)
    Base.metadata.drop_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(seed_demo, "engine", engine)
    monkeypatch.setattr(seed_demo, "SessionLocal", sessions)
    seed_demo.seed_demo("Term 3", "2026")
    def override_db():
        with sessions() as db:
            yield db
    app.dependency_overrides[get_db] = override_db
    with TestClient(app, raise_server_exceptions=False) as client:
        headers = {}
        for role in ("admin", "teacher", "parent"):
            result = client.post("/api/auth/login", json={"email_or_username": f"demo.{role}", "password": seed_demo.DEMO_PASSWORD})
            assert result.status_code == 200
            headers[role] = {"Authorization": "Bearer " + result.json()["access_token"]}
        with sessions() as db:
            users = {u.role.lower(): u.user_id for u in db.scalars(select(User))}
            students = {s.first_name: s.student_id for s in db.scalars(select(Student))}
        yield client, headers, users, students, sessions
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()

@pytest.mark.parametrize("role", ["ADMIN", "TEACHER", "PARENT"])
def test_create_list_and_login_all_roles(audit, role):
    c, h, _, _, _ = audit
    payload = dict(full_name="Audit Account", email_or_username="audit.account", password="AuditPass2026!", role=role)
    result = c.post("/api/admin/users", headers=h["admin"], json=payload)
    assert result.status_code == 201, result.text
    assert "password" not in result.text
    assert any(u["user_id"] == result.json()["user_id"] for u in c.get("/api/admin/users", headers=h["admin"]).json())
    assert c.post("/api/admin/users", headers=h["admin"], json=payload).status_code == 400
    login = c.post("/api/auth/login", json={k: payload[k] for k in ("email_or_username", "password")})
    assert login.status_code == 200 and login.json()["user"]["role"] == role

STUDENT = dict(admission_number="AUDIT-01", first_name="New", last_name="Learner", date_of_birth="2013-01-01", grade_level="Grade 7", stream="Demo East")

def test_student_create_list_duplicate(audit):
    c, h, _, _, _ = audit
    result = c.post("/api/admin/students", headers=h["admin"], json={**STUDENT, "admission_number": " AUDIT-01 "})
    assert result.status_code == 201 and result.json()["admission_number"] == "AUDIT-01"
    assert any(s["student_id"] == result.json()["student_id"] for s in c.get("/api/admin/students", headers=h["admin"]).json())
    assert c.post("/api/admin/students", headers=h["admin"], json=STUDENT).status_code == 400

@pytest.mark.parametrize("field,value", [("first_name", "   "), ("admission_number", ""), ("grade_level", " "), ("first_name", "X" * 101)])
def test_invalid_student_fields_do_not_write(audit, field, value):
    c, h, _, _, _ = audit
    before = len(c.get("/api/admin/students", headers=h["admin"]).json())
    result = c.post("/api/admin/students", headers=h["admin"], json={**STUDENT, field: value})
    assert result.status_code == 422, result.text
    assert len(c.get("/api/admin/students", headers=h["admin"]).json()) == before

def test_password_bcrypt_byte_limit(audit):
    c, h, _, _, _ = audit
    result = c.post("/api/admin/users", headers=h["admin"], json=dict(full_name="Audit", email_or_username="audit.long", password="é" * 40, role="PARENT"))
    assert result.status_code == 422, result.text
    assert c.post("/api/auth/login", json=dict(email_or_username="demo.parent", password="é" * 40)).status_code == 401

def test_assignment_create_read_delete_revokes_teacher_access(audit):
    c, h, users, students, _ = audit
    query = dict(grade_level="Grade 7", stream="Demo West")
    assert c.get("/api/teacher/students", params=query, headers=h["teacher"]).status_code == 403
    payload = dict(teacher_user_id=users["teacher"], **query, subject_name="Mathematics")
    result = c.post("/api/admin/teacher-assignments", headers=h["admin"], json=payload)
    assert result.status_code == 201, result.text
    key = result.json()["assignment_id"]
    assert c.post("/api/admin/teacher-assignments", headers=h["admin"], json=payload).status_code == 400
    assert c.post("/api/admin/teacher-assignments", headers=h["admin"], json={**payload, "teacher_user_id": users["parent"]}).status_code == 400
    assert c.get("/api/teacher/students", params=query, headers=h["teacher"]).status_code == 200
    assert any(a["assignment_id"] == key for a in c.get("/api/admin/teacher-assignments", headers=h["admin"]).json())
    assert c.delete(f"/api/admin/teacher-assignments/{key}", headers=h["parent"]).status_code == 403
    assert c.delete(f"/api/admin/teacher-assignments/{key}", headers=h["admin"]).status_code == 200
    assert all(a["assignment_id"] != key for a in c.get("/api/admin/teacher-assignments", headers=h["admin"]).json())
    assert c.get(f"/api/teacher/students/{students['Esther']}/assessments", headers=h["teacher"]).status_code == 403
    assert c.delete(f"/api/admin/teacher-assignments/{key}", headers=h["admin"]).status_code == 404

def test_link_create_read_delete_revokes_parent_access(audit):
    c, h, users, students, _ = audit
    payload = dict(parent_user_id=users["parent"], student_id=students["Brian"], relationship_type="Guardian")
    result = c.post("/api/admin/parent-links", headers=h["admin"], json=payload)
    assert result.status_code == 201
    key = result.json()["id"]
    listed = c.get("/api/admin/parent-links", headers=h["admin"])
    assert listed.status_code == 200, listed.text
    assert any(l["id"] == key for l in listed.json())
    assert c.post("/api/admin/parent-links", headers=h["admin"], json=payload).status_code == 400
    path = f"/api/parent/children/{students['Brian']}"
    assert c.get(path+"/progress", params=PERIOD, headers=h["parent"]).status_code == 200
    assert c.delete(f"/api/admin/parent-links/{key}", headers=h["teacher"]).status_code == 403
    assert c.delete(f"/api/admin/parent-links/{key}", headers=h["admin"]).status_code == 200
    for endpoint in (path+"/progress", path+"/assessments", f"/api/analytics/student/{students['Brian']}"):
        assert c.get(endpoint, params=PERIOD, headers=h["parent"]).status_code == 403
    assert c.delete(f"/api/admin/parent-links/{key}", headers=h["admin"]).status_code == 404

def test_teacher_records_create_read_and_authorization(audit):
    c, h, _, students, _ = audit
    student = students["Amina"]
    result = c.post("/api/teacher/assessments", headers=h["teacher"], json=dict(student_id=student, subject_name="Mathematics", **PERIOD, assessment_type="CAT", score=75, max_score=100, assessment_date="2026-09-22"))
    assert result.status_code == 200, result.text
    assert any(a["assessment_id"] == result.json()["assessment_id"] for a in c.get(f"/api/teacher/students/{student}/assessments", headers=h["teacher"]).json())
    result = c.post("/api/teacher/behaviour", headers=h["teacher"], json=dict(student_id=student, category="Participation", rating=2, record_date="2026-09-22"))
    assert result.status_code == 200
    assert any(b["record_id"] == result.json()["record_id"] for b in c.get(f"/api/teacher/students/{student}/behaviour", headers=h["teacher"]).json())
    result = c.post("/api/teacher/observations", headers=h["teacher"], json=dict(student_id=student, **PERIOD, observation_text="Audit classroom note", observation_date="2026-09-22"))
    assert result.status_code == 200
    assert any(n["observation_text"] == "Audit classroom note" for n in c.get(f"/api/teacher/students/{student}/observations", headers=h["teacher"]).json())
    for resource in ("assessments", "behaviour", "observations"):
        assert c.get(f"/api/teacher/students/{students['Esther']}/{resource}", headers=h["teacher"]).status_code == 403
        assert c.get(f"/api/teacher/students/999999/{resource}", headers=h["teacher"]).status_code == 404

def test_attendance_upsert_updates_single_record(audit):
    c, h, _, students, sessions = audit
    for status in ("Absent", "Present", "Present"):
        result = c.post("/api/teacher/attendance/bulk", headers=h["teacher"], json=dict(record_date="2026-09-22", entries=[dict(student_id=students["Amina"], status=status)]))
        assert result.status_code == 200
    with sessions() as db:
        records = list(db.scalars(select(Attendance).filter_by(student_id=students["Amina"], record_date="2026-09-22")))
        assert len(records) == 1 and records[0].status == "Present"

def test_duplicate_attendance_rejected_without_writes(audit):
    c, h, _, students, sessions = audit
    result = c.post("/api/teacher/attendance/bulk", headers=h["teacher"], json=dict(record_date="2026-09-23", entries=[dict(student_id=students["Amina"], status=s) for s in ("Absent", "Present")]))
    assert result.status_code == 422, result.text
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Attendance).filter_by(record_date="2026-09-23")) == 0

@pytest.mark.parametrize("role", ["admin", "teacher", "parent"])
def test_notifications_and_preferences_each_role(audit, role):
    c, h, users, _, sessions = audit
    with sessions() as db:
        key = NotificationService.send_notification(db, users[role], "SYSTEM", "LOW", "Audit notice", "Audit message").notification_id
    assert any(n["notification_id"] == key for n in c.get("/api/notifications", headers=h[role]).json())
    other = "parent" if role != "parent" else "teacher"
    assert c.patch(f"/api/notifications/{key}/read", headers=h[other]).status_code == 403
    assert c.patch(f"/api/notifications/{key}/read", headers=h[role]).json()["is_read"] is True
    assert c.patch(f"/api/notifications/{key}/read", headers=h[role]).status_code == 200
    assert c.patch("/api/notifications/999999/read", headers=h[role]).status_code == 404
    assert c.patch("/api/notifications/mark-all-read", headers=h[role]).status_code == 200
    assert c.get("/api/notifications/unread-count", headers=h[role]).json()["unread_count"] == 0
    result = c.put("/api/notifications/preferences", headers=h[role], json=dict(communication_style="concise", academic_updates=False))
    assert result.status_code == 200 and result.json()["communication_style"] == "CONCISE"
    assert c.get("/api/notifications/preferences", headers=h[role]).json()["academic_updates"] is False
    assert c.get("/api/notifications/preferences", headers=h[other]).json()["academic_updates"] is True
    assert c.put("/api/notifications/preferences", headers=h[role], json=dict(communication_style="invalid", notifications_enabled=False)).status_code == 400
    assert c.get("/api/notifications/preferences", headers=h[role]).json()["notifications_enabled"] is True

def test_role_restrictions_for_every_declared_role_endpoint(audit):
    c, h, _, _, _ = audit
    checked = 0
    for path, operations in app.openapi()["paths"].items():
        roles = ("teacher", "parent") if path.startswith("/api/admin/") else ("parent",) if path.startswith("/api/teacher/") else ("teacher",) if path.startswith("/api/parent/") else ()
        for method in operations.keys() & {"get", "post", "put", "patch", "delete"}:
            for role in roles:
                result = c.request(method.upper(), re.sub(r"\{[^}]+\}", "1", path), headers=h[role], json={})
                assert result.status_code == 403, (method, path, role, result.status_code, result.text)
                checked += 1
    assert checked >= 30
