"""
Automated Tests for Learning Path and Educational Resource Recommender.
"""

from __future__ import annotations

from datetime import date
import pytest
from fastapi.testclient import TestClient

from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.main import app
from app.models.academic import Assessment
from app.models.analytics import Recommendation
from app.models.behaviour import Attendance
from app.models.learning_path import LearningPathItem, LearningResource
from app.models.student import ParentStudent, Student, TeacherAssignment
from app.models.user import User
from app.services.expert_system import DEFAULT_REMEDIATION_BENCHMARK_PCT, ExpertSystemService
from app.services.learning_path_service import LearningPathService

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
        ("Grade 7 East Teacher", "teacher7", "TEACHER"),
        ("Grade 8 Teacher", "other_teacher", "TEACHER"),
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
        admission_number="ADM-LP-001",
        first_name="Kevin",
        last_name="Ochieng",
        date_of_birth=date(2012, 4, 12),
        gender="Male",
        grade_level="Grade 7",
        stream="East",
    )
    s2 = Student(
        admission_number="ADM-LP-002",
        first_name="Mercy",
        last_name="Chebet",
        date_of_birth=date(2012, 9, 21),
        gender="Female",
        grade_level="Grade 7",
        stream="West",
    )
    db.add(s1)
    db.add(s2)
    db.commit()

    # Parent 1 -> Kevin (Student 1)
    db.add(ParentStudent(parent_user_id=user_objs["parent1"].user_id, student_id=s1.student_id, relationship_type="Father"))
    # Parent 2 -> Mercy (Student 2)
    db.add(ParentStudent(parent_user_id=user_objs["parent2"].user_id, student_id=s2.student_id, relationship_type="Mother"))

    # Teacher 7 -> Grade 7 East (Kevin's class)
    db.add(TeacherAssignment(teacher_user_id=user_objs["teacher7"].user_id, grade_level="Grade 7", stream="East", subject_name="Mathematics"))
    db.add(TeacherAssignment(teacher_user_id=user_objs["teacher7"].user_id, grade_level="Grade 7", stream="East", subject_name="English"))

    # Other Teacher -> Grade 8 North
    db.add(TeacherAssignment(teacher_user_id=user_objs["other_teacher"].user_id, grade_level="Grade 8", stream="North", subject_name="Science"))

    # Add assessments for Kevin in Term 1 2026:
    # Mathematics = 36% (below benchmark), English = 42% (below benchmark), Science = 78% (above benchmark)
    for subj, score in [("Mathematics", 36.0), ("English", 42.0), ("Science", 78.0)]:
        db.add(Assessment(
            student_id=s1.student_id,
            subject_name=subj,
            academic_year="2026",
            term="Term 1",
            assessment_type="CAT 1",
            score=score,
            max_score=100.0,
            percentage=score,
            assessment_date=date(2026, 2, 10),
            recorded_by_teacher_id=user_objs["teacher7"].user_id,
        ))

    # Add 4 absences for Kevin
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


def test_starter_catalogue_endpoint(client, tokens):
    res = client.get("/api/analytics/learning-resources", headers=auth(tokens["teacher7"]))
    assert res.status_code == 200
    catalogue = res.json()
    assert len(catalogue) >= 5

    # Check required fields
    sample = catalogue[0]
    for field in [
        "resource_id", "subject_name", "grade_level", "topic_competency",
        "activity_title", "activity_description", "resource_title",
        "alignment_type", "is_verified", "suggested_duration", "recommended_next_step"
    ]:
        assert field in sample, f"Missing field {field} in resource item"

    # Test filtering by subject
    math_res = client.get("/api/analytics/learning-resources?subject=Mathematics", headers=auth(tokens["teacher7"]))
    assert math_res.status_code == 200
    math_items = math_res.json()
    assert all(item["subject_name"].lower() == "mathematics" for item in math_items)

    # Test filtering by alignment_type
    curriculum_res = client.get("/api/analytics/learning-resources?alignment_type=CURRICULUM_ALIGNED", headers=auth(tokens["teacher7"]))
    assert curriculum_res.status_code == 200
    curriculum_items = curriculum_res.json()
    assert all(item["alignment_type"] == "CURRICULUM_ALIGNED" for item in curriculum_items)


def test_learning_path_generation_on_calculation(client, tokens):
    # Teacher calculates analytics for Kevin (student_id = 1)
    calc_res = client.post(
        "/api/analytics/calculate/1",
        headers=auth(tokens["teacher7"]),
        json={"term": "Term 1", "academic_year": "2026"},
    )
    assert calc_res.status_code == 200, calc_res.text
    data = calc_res.json()

    assert "learning_path" in data
    learning_path = data["learning_path"]
    assert len(learning_path) >= 2, "Should have generated learning path items for failing subjects and risk indicators"

    # Kevin scored below benchmark in Mathematics (36%) and English (42%)
    subjects_in_path = {item["subject_name"] for item in learning_path}
    assert "Mathematics" in subjects_in_path, "Mathematics should be in learning path"
    assert "English" in subjects_in_path, "English should be in learning path"

    # Check mathematics learning path item details
    math_item = next(item for item in learning_path if item["subject_name"] == "Mathematics")
    assert "36.0%" in math_item["reason"] or "Mathematics" in math_item["reason"]
    assert len(math_item["activity_title"]) > 5
    assert len(math_item["activity_description"]) > 10
    assert len(math_item["resource_title"]) > 3
    assert math_item["alignment_type"] in ["CURRICULUM_ALIGNED", "PROVISIONAL_SUPPORT"]
    assert math_item["suggested_duration"] is not None
    assert math_item["recommended_next_step"] is not None

    # Check recommendations list also has embedded learning_path
    recs = data["recommendations"]
    assert any(r.get("learning_path") is not None for r in recs)


def test_get_learner_learning_path_endpoint(client, tokens):
    res = client.get(
        "/api/analytics/student/1/learning-path?term=Term%201&academic_year=2026",
        headers=auth(tokens["teacher7"]),
    )
    assert res.status_code == 200
    items = res.json()
    assert len(items) >= 2
    assert all(item["student_id"] == 1 for item in items)
    assert all(item["status"] == "Active" for item in items)


def test_duplicate_prevention_on_recalculation(client, tokens):
    # Fetch active learning path items before recalculation
    before_res = client.get(
        "/api/analytics/student/1/learning-path?term=Term%201&academic_year=2026",
        headers=auth(tokens["teacher7"]),
    )
    before_count = len(before_res.json())

    # Re-calculate analytics again immediately for Kevin
    calc_res = client.post(
        "/api/analytics/calculate/1",
        headers=auth(tokens["teacher7"]),
        json={"term": "Term 1", "academic_year": "2026"},
    )
    assert calc_res.status_code == 200

    # Fetch active learning path items after recalculation
    after_res = client.get(
        "/api/analytics/student/1/learning-path?term=Term%201&academic_year=2026",
        headers=auth(tokens["teacher7"]),
    )
    after_count = len(after_res.json())

    assert after_count == before_count, f"Duplicate active items created! Before: {before_count}, After: {after_count}"


def test_parent_access_authorization(client, tokens):
    # Parent 1 (linked to Kevin/student 1) must succeed
    p1_res = client.get(
        "/api/analytics/student/1/learning-path",
        headers=auth(tokens["parent1"]),
    )
    assert p1_res.status_code == 200
    assert len(p1_res.json()) >= 1

    # Parent 2 (linked to Mercy/student 2, NOT Kevin) must be forbidden (403)
    p2_res = client.get(
        "/api/analytics/student/1/learning-path",
        headers=auth(tokens["parent2"]),
    )
    assert p2_res.status_code == 403


def test_teacher_access_authorization(client, tokens):
    # Teacher 7 is assigned to Grade 7 East (Kevin's class) -> must succeed (200)
    t7_res = client.get(
        "/api/analytics/student/1/learning-path",
        headers=auth(tokens["teacher7"]),
    )
    assert t7_res.status_code == 200

    # Other Teacher is assigned to Grade 8 North (not Kevin's class) -> must be forbidden (403)
    other_res = client.get(
        "/api/analytics/student/1/learning-path",
        headers=auth(tokens["other_teacher"]),
    )
    assert other_res.status_code == 403


def test_missing_data_and_nonexistent_student(client, tokens):
    # Non-existent student -> 404
    non_existent = client.get(
        "/api/analytics/student/9999/learning-path",
        headers=auth(tokens["admin"]),
    )
    assert non_existent.status_code == 404

    # Mercy (student 2) has no assessments yet -> calculating returns 400
    calc_empty = client.post(
        "/api/analytics/calculate/2",
        headers=auth(tokens["admin"]),
        json={"term": "Term 1", "academic_year": "2026"},
    )
    assert calc_empty.status_code == 400
    assert "No assessment records found" in calc_empty.json()["detail"]


def test_student_analytics_query_embeds_learning_path(client, tokens):
    # Query student analytics via GET /api/analytics/student/1
    res = client.get("/api/analytics/student/1", headers=auth(tokens["parent1"]))
    assert res.status_code == 200
    data = res.json()

    assert "learning_path" in data
    assert len(data["learning_path"]) >= 2

    # Check curriculum alignment pill fields
    aligned_items = [lp for lp in data["learning_path"] if lp["alignment_type"] == "CURRICULUM_ALIGNED"]
    assert len(aligned_items) >= 1
    aligned = aligned_items[0]
    assert aligned["alignment_source"] is not None
    assert aligned["is_verified"] is True


def test_explanation_distinguishes_subject_evidence_from_topic_suggestion(client, tokens):
    """
    Verify recommendation explanation accuracy:
    - Identifies empirical subject assessment average that triggered the recommendation.
    - Mentions the system-defined remediation benchmark (not official CBC cutoff).
    - Explicitly distinguishes that topic-level assessments are not recorded in the database,
      and presents the suggested topic activity as a foundational focus area, NOT a confirmed weakness.
    - Includes practical next actions for parents and teachers.
    """
    res = client.get(
        "/api/analytics/student/1/learning-path?term=Term%201&academic_year=2026",
        headers=auth(tokens["teacher7"]),
    )
    assert res.status_code == 200
    items = res.json()

    math_item = next((i for i in items if i["subject_name"] == "Mathematics"), None)
    assert math_item is not None, "Mathematics item must be in learning path"

    reason = math_item["reason"]

    # 1. Evidence: Observed subject average
    assert "36.0%" in reason
    assert "Mathematics" in reason

    # 2. Benchmark description: System-defined remediation benchmark
    assert "system-defined remediation benchmark" in reason.lower()
    assert "50.0%" in reason

    # 3. Transparent distinction: sub-topic assessments are not recorded; suggested support, not confirmed weakness
    assert "not as a confirmed topic weakness" in reason.lower() or "not a confirmed" in reason.lower()
    assert "sub-topic assessments are not recorded" in reason.lower()

    # 4. Actionable next steps
    assert "recommended next action" in reason.lower()
    assert math_item["recommended_next_step"] is not None
    assert len(math_item["recommended_next_step"]) > 10


def test_configurable_remediation_benchmark_direct():
    """
    Verify that the remediation benchmark is fully configurable and alters
    subject deficiency identification accordingly.
    """
    db = SessionLocal()
    try:
        student = db.query(Student).filter(Student.admission_number == "ADM-LP-001").first()
        assert student is not None

        # Kevin's scores: Mathematics = 36.0%, English = 42.0%, Science = 78.0%

        # Scenario A: Benchmark set below all scores (30.0%)
        # Neither 36% nor 42% falls below 30.0%
        rec_dummy = Recommendation(
            student_id=student.student_id,
            term="Term 1",
            academic_year="2026",
            rule_code="ACAD_SUBJECT_DEFICIENCY",
            recommendation_text="Test deficiency",
            target_audience="Both",
            priority="High",
            status="Active",
        )
        db.add(rec_dummy)
        db.commit()

        items_low = LearningPathService.generate_learning_paths_for_recommendations(
            db=db,
            student=student,
            term="Term 1",
            academic_year="2026",
            recommendations=[rec_dummy],
            remediation_benchmark=30.0,
        )
        # When no subjects are < 30.0%, it falls back to the lowest subject (Mathematics at 36%)
        # but the reason states the 30.0% benchmark
        assert len(items_low) == 1
        assert "30.0%" in items_low[0].reason

        # Scenario B: Benchmark set to 80.0% (all three subjects fall below 80%)
        items_high = LearningPathService.generate_learning_paths_for_recommendations(
            db=db,
            student=student,
            term="Term 1",
            academic_year="2026",
            recommendations=[rec_dummy],
            remediation_benchmark=80.0,
        )
        # All three subjects (Mathematics 36%, English 42%, Science 78%) must be included
        subjects_high = {i.subject_name for i in items_high}
        assert subjects_high == {"Mathematics", "English", "Science"}
        assert all("80.0%" in i.reason for i in items_high)

    finally:
        db.close()


def test_curriculum_alignment_audit_and_classification(client, tokens):
    """
    Verify strict curriculum alignment audit:
    - Official CBC alignment (CURRICULUM_ALIGNED) is ONLY claimed where supported
      by a specific, identifiable KICD Curriculum Design publication and strand/sub-strand.
    - General materials from the Kenya Education Cloud and external OERs
      are classified as provisional supplementary support (PROVISIONAL_SUPPORT).
    """
    res = client.get("/api/analytics/learning-resources", headers=auth(tokens["teacher7"]))
    assert res.status_code == 200
    catalogue = res.json()

    # Find verified curriculum-aligned items
    aligned_items = [r for r in catalogue if r["alignment_type"] == "CURRICULUM_ALIGNED"]
    assert len(aligned_items) >= 1

    for item in aligned_items:
        # Must be verified
        assert item["is_verified"] is True
        # Must cite a specific official KICD syllabus/design publication, not just a generic portal name
        source = item["alignment_source"]
        assert "KICD Junior Secondary School Curriculum Design" in source or "Curriculum Design" in source
        assert "Strand" in source

    # Check downgraded / provisional resources
    provisional_items = [r for r in catalogue if r["alignment_type"] == "PROVISIONAL_SUPPORT"]
    assert len(provisional_items) >= 4

    # Verify that general Kenya Education Cloud materials without specific syllabus sections
    # are classified as PROVISIONAL_SUPPORT
    kec_english = next(
        (r for r in catalogue if r["subject_name"] == "English" and "Kenya Education Cloud" in r["resource_title"]),
        None,
    )
    if kec_english:
        assert kec_english["alignment_type"] == "PROVISIONAL_SUPPORT"
        assert "provisional supplementary support" in kec_english["alignment_source"].lower()
        assert kec_english["is_verified"] is False

    kec_science = next(
        (r for r in catalogue if r["subject_name"] == "Science" and "Kenya Education Cloud" in r["resource_title"]),
        None,
    )
    if kec_science:
        assert kec_science["alignment_type"] == "PROVISIONAL_SUPPORT"
        assert "provisional supplementary support" in kec_science["alignment_source"].lower()
        assert kec_science["is_verified"] is False

    kec_enrichment = next(
        (r for r in catalogue if r["subject_name"] == "Academic Enrichment"),
        None,
    )
    if kec_enrichment:
        assert kec_enrichment["alignment_type"] == "PROVISIONAL_SUPPORT"
        assert "provisional supplementary support" in kec_enrichment["alignment_source"].lower()
        assert kec_enrichment["is_verified"] is False
