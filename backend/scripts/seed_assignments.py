"""Add repeatable fictional assignment examples after seed_demo has created its accounts."""
from datetime import timedelta, datetime
from sqlalchemy import select
from app.core.academic_calendar import term_date_range
from app.models.assignment import ClassAssignment
from app.models.student import Student
from app.models.user import User
from app.services.assignment_service import add_recipient, notify_follow_up
from app.services import assignment_service
from app.services.lifecycle_service import record_change


def seed_assignments(db, term, year):
    teacher = db.scalar(select(User).filter_by(email_or_username="demo.teacher"))
    if not teacher or teacher.full_name != "Fictional Demo Teacher" or teacher.role != "TEACHER":
        raise RuntimeError("Run seed_demo first; the fictional demo teacher is required.")
    learners = list(db.scalars(select(Student).where(Student.admission_number.in_([f"DEMO-{i:03}" for i in range(1, 5)]))))
    if len(learners) != 4 or any(s.last_name != "Demo" or s.stream != "Demo East" for s in learners):
        raise RuntimeError("Expected the original fictional Demo East learner fixtures; no assignment records written.")
    start, end = term_date_range(term, year)
    anchor = min(max(assignment_service.school_today(), start), end)
    assigned = max(start, anchor - timedelta(days=10))
    missing_due = max(start, anchor - timedelta(days=3))
    future_due = min(end, anchor + timedelta(days=7))
    specs = [("Demo: Fractions practice", "Mathematics", missing_due),
             ("Demo: Reading reflection", "English", future_due),
             ("Demo: Number exercises", "Mathematics", missing_due)]
    result = []
    for title, subject, due in specs:
        row = db.scalar(select(ClassAssignment).filter_by(title=title, subject_name=subject,
            grade_level="Grade 7", stream="Demo East", term=term, academic_year=year,
            created_by_teacher_id=teacher.user_id))
        if row is None:
            row = ClassAssignment(title=title, instructions="Fictional assignment for demonstrating completion tracking; no marks are recorded here.",
                grade_level="Grade 7", stream="Demo East", subject_name=subject, term=term,
                academic_year=year, assigned_date=assigned, due_date=due, created_by_teacher_id=teacher.user_id)
            db.add(row); db.flush()
            record_change(db, teacher, row, "create")
            for student in learners:
                completion = add_recipient(db, row, student)
                if title.endswith("Number exercises") and student.first_name in ("Amina", "David") and assigned <= assignment_service.school_today():
                    completion.status = "SUBMITTED"
                    completion.submitted_on = min(anchor, assignment_service.school_today())
                    completion.reason = "Fictional example: learner needed additional time after illness."
                    completion.recorded_by_teacher_id = teacher.user_id
                elif title.endswith("Fractions practice") and student.first_name == "Brian" and due <= assignment_service.school_today():
                    completion.status = "SUBMITTED"
                    completion.submitted_on = due
                    completion.recorded_by_teacher_id = teacher.user_id
                elif title.endswith("Fractions practice") and student.first_name == "Cynthia":
                    completion.status = "EXCUSED"
                    completion.reason = "Fictional example: alternate classroom task."
                    completion.recorded_by_teacher_id = teacher.user_id
        result.append(row.assignment_id)
    db.commit()
    notify_follow_up(db, [s.student_id for s in learners], term, year)
    return result
