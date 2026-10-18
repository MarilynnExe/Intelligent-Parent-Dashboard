"""
End-to-end API tests.

Drives the real FastAPI app over HTTP as an admin, a teacher and a parent:
authentication and role checks, admin management, teacher data capture,
risk analytics and the parent view.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.main import app
from app.models.user import User

PASSWORD = "pass1234"


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    for name, username, role in [
        ("System Administrator", "admin", "ADMIN"),
        ("Test Teacher", "teacher", "TEACHER"),
        ("Test Parent", "parent", "PARENT"),
    ]:
        db.add(User(full_name=name, email_or_username=username,
                    password_hash=hash_password(PASSWORD), role=role))
    db.commit()
    db.close()

    return TestClient(app)


def login(client, username, password=PASSWORD):
    return client.post("/api/auth/login", json={"email_or_username": username, "password": password})


@pytest.fixture(scope="module")
def tokens(client):
    return {u: login(client, u).json()["access_token"] for u in ("admin", "teacher", "parent")}


@pytest.fixture(scope="module")
def school(client, tokens):
    """Enroll a Grade 7 cohort, assign the teacher to East, link the parent to Amina."""
    admin = auth(tokens["admin"])
    users = {u["email_or_username"]: u["user_id"] for u in client.get("/api/admin/users", headers=admin).json()}

    students = {}
    for adm, first, last, stream in [
        ("ADM001", "Amina", "Otieno", "East"),
        ("ADM002", "Brian", "Kamau", "East"),
        ("ADM003", "Cynthia", "Wanjiru", "East"),
        ("ADM004", "David", "Mwangi", "East"),
        ("ADM005", "Esther", "Njeri", "West"),
    ]:
        r = client.post("/api/admin/students", headers=admin, json={
            "admission_number": adm, "first_name": first, "last_name": last,
            "date_of_birth": "2013-03-01", "grade_level": "Grade 7", "stream": stream,
        })
        assert r.status_code == 201, r.text
        students[first] = r.json()["student_id"]

    for subject in ("Mathematics", "English"):
        r = client.post("/api/admin/teacher-assignments", headers=admin, json={
            "teacher_user_id": users["teacher"], "grade_level": "Grade 7",
            "stream": "East", "subject_name": subject,
        })
        assert r.status_code == 201, r.text

    r = client.post("/api/admin/parent-links", headers=admin, json={
        "parent_user_id": users["parent"], "student_id": students["Amina"], "relationship_type": "Mother",
    })
    assert r.status_code == 201, r.text

    teacher = auth(tokens["teacher"])
    scores = {"Amina": (38, 42), "Brian": (65, 70), "Cynthia": (88, 92), "David": (55, 50)}
    for name, (maths, english) in scores.items():
        for subject, score in (("Mathematics", maths), ("English", english)):
            r = client.post("/api/teacher/assessments", headers=teacher, json={
                "student_id": students[name], "subject_name": subject, "academic_year": "2026",
                "term": "Term 1", "assessment_type": "CAT", "score": score, "max_score": 100,
                "assessment_date": "2026-02-10",
            })
            assert r.status_code == 200, r.text

    return {"users": users, "students": students}


# ---------------------------------------------------------------------------
# Authentication & role-based access
# ---------------------------------------------------------------------------

def test_login_rejects_bad_credentials(client):
    assert login(client, "admin").status_code == 200
    assert login(client, "admin", "wrong-password").status_code == 401
    assert login(client, "nobody").status_code == 401


def test_invalid_or_missing_token_is_rejected(client):
    assert client.get("/api/admin/stats", headers=auth("not.a.token")).status_code == 401
    assert client.get("/api/admin/stats").status_code == 401


def test_auth_me_uses_bearer_header(client, tokens):
    r = client.get("/api/auth/me", headers=auth(tokens["teacher"]))
    assert r.status_code == 200
    assert r.json()["role"] == "TEACHER"
    # The token must never be accepted from the URL
    assert client.get("/api/auth/me", params={"token": tokens["teacher"]}).status_code == 401


@pytest.mark.parametrize("role, method, path", [
    ("teacher", "get", "/api/admin/users"),
    ("parent", "get", "/api/admin/users"),
    ("parent", "get", "/api/teacher/assignments"),
    ("parent", "post", "/api/analytics/calculate/1"),
])
def test_roles_are_enforced(client, tokens, role, method, path):
    r = getattr(client, method)(path, headers=auth(tokens[role]))
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Admin management
# ---------------------------------------------------------------------------

def test_admin_user_creation_validation(client, tokens):
    admin = auth(tokens["admin"])
    new_user = {"full_name": "Jane Teacher", "email_or_username": "jane", "password": "longenough", "role": "teacher"}

    r = client.post("/api/admin/users", headers=admin, json=new_user)
    assert r.status_code == 201
    assert r.json()["role"] == "TEACHER"

    assert client.post("/api/admin/users", headers=admin, json=new_user).status_code == 400  # duplicate
    assert client.post("/api/admin/users", headers=admin,
                       json={**new_user, "email_or_username": "x1", "role": "JANITOR"}).status_code == 400
    assert client.post("/api/admin/users", headers=admin,
                       json={**new_user, "email_or_username": "x2", "password": ""}).status_code == 422
    assert client.post("/api/admin/users", headers=admin,
                       json={**new_user, "email_or_username": "x3", "password": "short"}).status_code == 422
    assert client.post("/api/admin/users", headers=admin,
                       json={**new_user, "email_or_username": "   "}).status_code == 422


def test_admin_lists_and_links(client, tokens, school):
    admin = auth(tokens["admin"])
    assert len(client.get("/api/admin/students", headers=admin).json()) == 5
    assert len(client.get("/api/admin/teacher-assignments", headers=admin).json()) == 2

    links = client.get("/api/admin/parent-links", headers=admin).json()
    assert [l["student_name"] for l in links] == ["Amina Otieno"]

    # Duplicate admission number and linking a non-parent are rejected
    assert client.post("/api/admin/students", headers=admin, json={
        "admission_number": "ADM001", "first_name": "X", "last_name": "Y",
        "date_of_birth": "2013-03-01", "grade_level": "Grade 7",
    }).status_code == 400
    assert client.post("/api/admin/parent-links", headers=admin, json={
        "parent_user_id": school["users"]["teacher"], "student_id": school["students"]["Brian"],
    }).status_code == 400

    stats = client.get("/api/admin/stats", headers=admin).json()
    assert stats["total_students"] == 5
    assert stats["total_assessments"] == 8


# ---------------------------------------------------------------------------
# Teacher data capture
# ---------------------------------------------------------------------------

def test_teacher_is_scoped_to_assigned_classes(client, tokens, school):
    teacher = auth(tokens["teacher"])
    east = client.get("/api/teacher/students", headers=teacher, params={"grade_level": "Grade 7", "stream": "East"})
    assert east.status_code == 200 and len(east.json()) == 4
    west = client.get("/api/teacher/students", headers=teacher, params={"grade_level": "Grade 7", "stream": "West"})
    assert west.status_code == 403

    r = client.post("/api/teacher/assessments", headers=teacher, json={
        "student_id": school["students"]["Esther"], "subject_name": "Mathematics", "academic_year": "2026",
        "term": "Term 1", "assessment_type": "CAT", "score": 50, "max_score": 100,
    })
    assert r.status_code == 403


def test_assessment_validation(client, tokens, school):
    teacher = auth(tokens["teacher"])
    base = {"student_id": school["students"]["Amina"], "academic_year": "2026", "term": "Term 1",
            "assessment_type": "CAT", "max_score": 100}
    assert client.post("/api/teacher/assessments", headers=teacher,
                       json={**base, "subject_name": "Mathematics", "score": 120}).status_code == 400
    assert client.post("/api/teacher/assessments", headers=teacher,
                       json={**base, "subject_name": "Kiswahili", "score": 50}).status_code == 403


def test_bulk_attendance_validates_and_reports_skips(client, tokens, school):
    teacher = auth(tokens["teacher"])
    s = school["students"]
    r = client.post("/api/teacher/attendance/bulk", headers=teacher, json={
        "record_date": "2026-02-02",
        "entries": [{"student_id": s["Brian"], "status": "Present"},
                    {"student_id": s["Esther"], "status": "Absent"}],  # Esther is in West
    })
    assert r.status_code == 200
    assert r.json()["updated"] == 1
    assert r.json()["skipped_student_ids"] == [s["Esther"]]

    r = client.post("/api/teacher/attendance/bulk", headers=teacher, json={
        "record_date": "2026-02-02", "entries": [{"student_id": s["Brian"], "status": "absent"}],
    })
    assert r.status_code == 422


def test_behaviour_and_observations_round_trip(client, tokens, school):
    teacher = auth(tokens["teacher"])
    amina = school["students"]["Amina"]

    r = client.post("/api/teacher/behaviour", headers=teacher, json={
        "student_id": amina, "category": "Participation", "rating": 2, "teacher_note": "Withdrawn",
        "record_date": "2026-02-12",
    })
    assert r.status_code == 200
    assert client.post("/api/teacher/behaviour", headers=teacher, json={
        "student_id": amina, "category": "Participation", "rating": 9,
    }).status_code == 422

    r = client.post("/api/teacher/observations", headers=teacher, json={
        "student_id": amina, "term": "Term 1", "academic_year": "2026",
        "observation_text": "Struggles with fractions",
    })
    assert r.status_code == 200

    behaviour = client.get(f"/api/teacher/students/{amina}/behaviour", headers=teacher).json()
    assert [(b["category"], b["rating"]) for b in behaviour] == [("Participation", 2)]
    observations = client.get(f"/api/teacher/students/{amina}/observations", headers=teacher).json()
    assert [o["observation_text"] for o in observations] == ["Struggles with fractions"]

    esther = school["students"]["Esther"]
    assert client.get(f"/api/teacher/students/{esther}/behaviour", headers=teacher).status_code == 403
    assert client.get(f"/api/teacher/students/{esther}/observations", headers=teacher).status_code == 403


# ---------------------------------------------------------------------------
# Risk analytics
# ---------------------------------------------------------------------------

def calculate(client, token, student_id, term="Term 1", year="2026"):
    return client.post(f"/api/analytics/calculate/{student_id}", headers=auth(token),
                       json={"term": term, "academic_year": year})


def test_analytics_pipeline(client, tokens, school):
    s = school["students"]
    for day in ("2026-02-03", "2026-02-04", "2026-02-05"):
        client.post("/api/teacher/attendance/bulk", headers=auth(tokens["teacher"]), json={
            "record_date": day, "entries": [{"student_id": s["Amina"], "status": "Absent"}],
        })
    client.post("/api/teacher/behaviour", headers=auth(tokens["teacher"]), json={
        "student_id": s["Amina"], "category": "Conduct", "rating": 1,
    })

    results = {}
    for name in ("Amina", "Brian", "Cynthia", "David"):
        r = calculate(client, tokens["teacher"], s[name])
        assert r.status_code == 200, r.text
        results[name] = r.json()

    weak, strong = results["Amina"], results["Cynthia"]
    assert weak["support_probability"] > strong["support_probability"]
    assert weak["cohort_percentile"] < strong["cohort_percentile"]
    assert weak["absences_count"] == 3
    assert {"ACAD_SUBJECT_DEFICIENCY", "ATTEND_EXCESSIVE_ABSENCE", "BEHAV_ATTENTION_REQUIRED"} <= {
        r["rule_code"] for r in weak["recommendations"]
    }

    # Access rules for running analytics
    assert calculate(client, tokens["teacher"], s["Esther"]).status_code == 403
    assert calculate(client, tokens["teacher"], s["Amina"], term="Term 2").status_code == 400


def test_percentile_refreshes_after_new_assessments(client, tokens, school):
    amina = school["students"]["Amina"]
    before = calculate(client, tokens["teacher"], amina).json()["cohort_percentile"]

    for subject in ("Mathematics", "English"):
        client.post("/api/teacher/assessments", headers=auth(tokens["teacher"]), json={
            "student_id": amina, "subject_name": subject, "academic_year": "2026", "term": "Term 1",
            "assessment_type": "Exam", "score": 100, "max_score": 100, "assessment_date": "2026-03-20",
        })

    after = calculate(client, tokens["teacher"], amina).json()["cohort_percentile"]
    assert after > before


def test_absences_from_other_terms_are_ignored(client, tokens, school):
    brian = school["students"]["Brian"]
    client.post("/api/teacher/attendance/bulk", headers=auth(tokens["teacher"]), json={
        "record_date": "2025-06-01", "entries": [{"student_id": brian, "status": "Absent"}],
    })
    assert calculate(client, tokens["teacher"], brian).json()["absences_count"] == 0


# ---------------------------------------------------------------------------
# Parent view
# ---------------------------------------------------------------------------

def test_parent_sees_only_linked_child(client, tokens, school):
    parent = auth(tokens["parent"])
    s = school["students"]

    children = client.get("/api/parent/my-children", headers=parent).json()
    assert [c["student_id"] for c in children] == [s["Amina"]]

    assert client.get(f"/api/parent/children/{s['Amina']}/assessments", headers=parent).status_code == 200
    assert client.get(f"/api/parent/children/{s['Brian']}/assessments", headers=parent).status_code == 403
    assert client.get(f"/api/analytics/student/{s['Brian']}", headers=parent).status_code == 403


def test_parent_gets_latest_analytics_without_naming_a_term(client, tokens, school):
    r = client.get(f"/api/analytics/student/{school['students']['Amina']}", headers=auth(tokens["parent"]))
    assert r.status_code == 200
    data = r.json()
    assert (data["term"], data["academic_year"]) == ("Term 1", "2026")
    assert data["recommendations"]
