"""Explicit, additive, repeatable fictional demo setup; never resets school data."""
import argparse
from datetime import date, timedelta

from sqlalchemy import select

from app.core.academic_calendar import term_date_range, term_for_date
from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app import models  # Register all tables, including the additive freshness table.
from app.models.academic import Assessment
from app.models.behaviour import Attendance, BehaviourRecord
from app.models.student import ParentStudent, Student, TeacherAssignment
from app.models.user import User
from app.services.analytics_service import invalidate, refresh_students

DEMO_PASSWORD = "DemoSchool2026!"


def seed_demo(term, academic_year):
    start, _ = term_date_range(term, academic_year)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        users = {}
        # Preflight collisions before writing anything. Existing demo passwords are preserved.
        for role in ("ADMIN", "TEACHER", "PARENT"):
            username = f"demo.{role.lower()}"
            name = f"Fictional Demo {role.title()}"
            user = db.scalar(select(User).filter_by(email_or_username=username))
            if user and (user.full_name != name or user.role != role):
                raise RuntimeError(f"Username {username} already belongs to another account; no changes made.")
            users[role] = user or User(full_name=name, email_or_username=username,
                password_hash=hash_password(DEMO_PASSWORD), role=role)
        learners = []
        for number, name in enumerate(("Amina", "Brian", "Cynthia", "David", "Esther"), 1):
            admission = f"DEMO-{number:03}"
            student = db.scalar(select(Student).filter_by(admission_number=admission))
            stream = "Demo East" if number < 5 else "Demo West"
            if student and (student.first_name != name or student.last_name != "Demo" or
                            student.grade_level != "Grade 7" or student.stream != stream):
                raise RuntimeError(f"Admission {admission} belongs to another learner; no changes made.")
            learners.append(student or Student(admission_number=admission, first_name=name,
                last_name="Demo", date_of_birth=date(2013, 3, number), grade_level="Grade 7", stream=stream))
        db.add_all(list(users.values()) + learners)
        db.flush()
        teacher = users["TEACHER"]
        for subject in ("Mathematics", "English"):
            key = dict(teacher_user_id=teacher.user_id, grade_level="Grade 7", stream="Demo East", subject_name=subject)
            if not db.scalar(select(TeacherAssignment).filter_by(**key)):
                db.add(TeacherAssignment(**key))
        for student in (learners[0], learners[3]):
            key = dict(parent_user_id=users["PARENT"].user_id, student_id=student.student_id)
            if not db.scalar(select(ParentStudent).filter_by(**key)):
                db.add(ParentStudent(**key, relationship_type="Guardian"))
        for student, average in zip(learners[:3], (35, 65, 90)):
            for offset, delta in ((7, -5), (14, 5)):
                for subject in ("Mathematics", "English"):
                    key = dict(student_id=student.student_id, subject_name=subject, term=term,
                               academic_year=academic_year, assessment_type="Demo CAT", assessment_date=start + timedelta(days=offset))
                    if not db.scalar(select(Assessment).filter_by(**key)):
                        db.add(Assessment(**key, score=average + delta, max_score=100,
                            percentage=average + delta, recorded_by_teacher_id=teacher.user_id))
            for offset in range(5, 11):
                key = dict(student_id=student.student_id, record_date=start + timedelta(days=offset))
                if not db.scalar(select(Attendance).filter_by(**key)):
                    db.add(Attendance(**key, status="Absent" if student == learners[0] and offset < 8 else "Present",
                        recorded_by_teacher_id=teacher.user_id, remarks="Fictional demo record"))
        key = dict(student_id=learners[0].student_id, record_date=start + timedelta(days=10), category="Engagement")
        if not db.scalar(select(BehaviourRecord).filter_by(**key)):
            db.add(BehaviourRecord(**key, rating=2, teacher_note="Fictional demo observation",
                recorded_by_teacher_id=teacher.user_id))
        invalidate(db, learners[:4], term, academic_year)
        db.commit()
        results = refresh_students(db, learners[:4], term, academic_year)
        return {"period": f"{term} {academic_year}", "analytics": results}


if __name__ == "__main__":
    current_term, current_year = term_for_date(date.today())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--term", choices=["Term 1", "Term 2", "Term 3"], default=current_term)
    parser.add_argument("--year", default=current_year)
    parser.add_argument("--with-assignments", action="store_true", help="Also add fictional assignment-completion examples without resetting existing work.")
    parser.add_argument("--with-competencies", action="store_true", help="Also add fictional teacher-defined skills and dated evidence; preserve existing corrections.")
    args = parser.parse_args()
    print(seed_demo(args.term, args.year))
    if args.with_assignments:
        from scripts.seed_assignments import seed_assignments
        with SessionLocal() as db:
            print("Demo assignment IDs:", seed_assignments(db, args.term, args.year))
    if args.with_competencies:
        from scripts.seed_competencies import seed_competencies
        with SessionLocal() as db:
            print("Demo competency IDs:", seed_competencies(db, args.term, args.year))
    print("Demo usernames: demo.admin / demo.teacher / demo.parent")
    print(f"Initial demo password: {DEMO_PASSWORD} (existing passwords are never reset)")
