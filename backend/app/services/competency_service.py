"""Recorded competency summaries; never impute levels from academic marks."""
import logging
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import or_, and_
from app.core.academic_calendar import term_date_range
from app.models.competency import Competency, CompetencyObservation
from app.models.student import Student, TeacherAssignment, ParentStudent
from app.models.notification import Notification
from app.services import assignment_service
from app.services.lifecycle_service import active_students, require_active_student, snapshot
from app.services.notification_service import NotificationService

LEVELS = ["BELOW_EXPECTATIONS", "APPROACHING_EXPECTATIONS", "MEETING_EXPECTATIONS", "EXCEEDING_EXPECTATIONS"]

def access(db, actor, competency):
    if not db.query(TeacherAssignment).filter_by(teacher_user_id=actor.user_id,
        grade_level=competency.grade_level, stream=competency.stream, subject_name=competency.subject_name).first():
        raise HTTPException(status_code=403, detail="You are not assigned to this class and subject.")

def learner_access(db, competency, student_id):
    student = db.get(Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Learner not found.")
    require_active_student(db, student)
    if (student.grade_level, student.stream) != (competency.grade_level, competency.stream):
        raise HTTPException(status_code=403, detail="Transferred learners' competency history is read-only.")
    return student

def validate_date(data):
    start, end = term_date_range(data.term, data.academic_year)
    if not start <= data.observed_on <= end or data.observed_on > assignment_service.school_today():
        raise HTTPException(status_code=400, detail="Observation date must be in the selected term/year and cannot be in the future.")

def summary(db, student, term, academic_year):
    # Current-class catalog plus previously observed skills preserve transfer history.
    observations = db.query(CompetencyObservation).filter_by(student_id=student.student_id,
        term=term, academic_year=academic_year).order_by(CompetencyObservation.observed_on, CompetencyObservation.observation_id).all()
    by_comp = {}
    for row in observations:
        by_comp.setdefault(row.competency_id, []).append(snapshot(row))
    catalog = db.query(Competency).filter(Competency.is_archived.is_(False),
        or_(and_(Competency.grade_level == student.grade_level, Competency.stream == student.stream),
            Competency.competency_id.in_(list(by_comp)))).order_by(Competency.subject_name, Competency.strand, Competency.name).all()
    items, counts, guidance = [], {k: 0 for k in LEVELS + ["NOT_ASSESSED"]}, []
    for skill in catalog:
        current_class = (student.grade_level, student.stream) == (skill.grade_level, skill.stream)
        history = by_comp.get(skill.competency_id, [])
        if not current_class and not history:
            continue
        latest = history[-1] if history else None
        level = latest["level"] if latest else "NOT_ASSESSED"
        counts[level] += 1
        change = None
        if len(history) > 1:
            delta = LEVELS.index(history[-1]["level"]) - LEVELS.index(history[-2]["level"])
            change = "Improved" if delta > 0 else "Needs renewed support" if delta < 0 else "Same level"
        items.append({**snapshot(skill), "current_class": current_class, "latest": latest, "history": history, "change": change})
        if level in LEVELS[:2]:
            guidance.append({"rule_code": "COMPETENCY_PRACTICE", "competency_id": skill.competency_id,
                "text": f"Practise {skill.name} in {skill.subject_name} using a short teacher-agreed activity. Review the recorded evidence together and ask the teacher when to reassess."})
    return {"term": term, "academic_year": academic_year, "as_of": assignment_service.school_today(),
        "rubric_source": "Teacher-defined classroom rubric; official curriculum mapping has not been verified.",
        "counts": counts, "competencies": items, "guidance": guidance}

def notify(db, student, term, academic_year):
    failed = False
    for link in db.query(ParentStudent).filter_by(student_id=student.student_id).all():
        try:
            data = summary(db, student, term, academic_year)
            needs = [item["name"] for item in data["competencies"] if item["latest"] and item["latest"]["level"] in LEVELS[:2]]
            key = f"competency:{link.parent_user_id}:{student.student_id}:{academic_year}:{term}"
            if needs:
                names = ", ".join(needs[:3])
                NotificationService.send_notification(db, recipient_user_id=link.parent_user_id,
                    category="ACADEMIC", priority="MEDIUM", title="Competency practice update",
                    message_detailed=f"{student.first_name}'s recorded classroom evidence suggests practice in: {names}. Review the Competencies tab with your child's teacher.",
                    message_concise=f"{student.first_name}: review competency practice guidance.",
                    suggested_action="Review the competency evidence and agree on a practice activity with the teacher.",
                    student_id=student.student_id, source_ref="competency_tracking", dedup_key=key)
            else:
                for alert in db.query(Notification).filter_by(dedup_key=key, is_read=False).all():
                    alert.is_read, alert.read_at = True, datetime.utcnow()
                db.commit()
        except Exception:
            db.rollback()
            logging.getLogger(__name__).exception("Competency notification failed after records were committed")
            failed = True
    return {"status": "retry_needed" if failed else "complete"}
