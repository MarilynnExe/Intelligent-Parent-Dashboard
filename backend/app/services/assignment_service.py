"""Completion-based monitoring. Does not change CatBoost inputs or stored predictions."""
from datetime import datetime
from zoneinfo import ZoneInfo
import logging
from fastapi import HTTPException
from app.models.assignment import ClassAssignment, AssignmentCompletion
from app.models.student import Student, ParentStudent, TeacherAssignment
from app.models.notification import Notification
from app.services.lifecycle_service import active_students, archived, record_change, snapshot
from app.services.notification_service import NotificationService
from app.services.expert_system import ExpertSystemService

logger = logging.getLogger(__name__)


def school_today():
    return datetime.now(ZoneInfo("Africa/Nairobi")).date()


def assignment_access(db, teacher, assignment):
    allowed = db.query(TeacherAssignment).filter_by(teacher_user_id=teacher.user_id,
        grade_level=assignment.grade_level, stream=assignment.stream, subject_name=assignment.subject_name).first()
    if not allowed:
        raise HTTPException(status_code=403, detail="You are not assigned to this class and subject.")


def recipient_editable(db, assignment, student):
    return (not assignment.is_withdrawn and not archived(db, student.student_id)
            and student.grade_level == assignment.grade_level and student.stream == assignment.stream)


def display_status(assignment, completion, today=None):
    today = today or school_today()
    if assignment.is_withdrawn:
        return "WITHDRAWN"
    if completion.status == "EXCUSED":
        return "EXCUSED"
    if completion.status == "SUBMITTED":
        return "LATE" if completion.submitted_on > assignment.due_date else "SUBMITTED"
    return "MISSING" if today > assignment.due_date else "PENDING"


def add_recipient(db, assignment, student):
    existing = db.query(AssignmentCompletion).filter_by(assignment_id=assignment.assignment_id, student_id=student.student_id).first()
    if existing:
        return existing
    row = AssignmentCompletion(assignment_id=assignment.assignment_id, student_id=student.student_id,
        status="NOT_SUBMITTED", updated_at=datetime.utcnow())
    db.add(row)
    db.flush()
    return row


def sync_assignment_roster(db, assignment):
    """Explicit teacher action: retain recipients and add current learners if not overdue."""
    if assignment.is_withdrawn or assignment.due_date < school_today():
        return
    for student in db.query(Student).filter(active_students()).filter_by(
            grade_level=assignment.grade_level, stream=assignment.stream).all():
        add_recipient(db, assignment, student)


def sync_new_learner(db, student):
    """Called transactionally on enrollment, class change and restore; never on a GET."""
    if archived(db, student.student_id):
        return
    assignments = db.query(ClassAssignment).filter_by(grade_level=student.grade_level,
        stream=student.stream, is_withdrawn=False).filter(ClassAssignment.due_date >= school_today()).all()
    for assignment in assignments:
        add_recipient(db, assignment, student)


def validate_submission(assignment, entry):
    if entry.status != "SUBMITTED":
        return
    if not (assignment.assigned_date <= entry.submitted_on <= school_today()):
        raise HTTPException(status_code=400, detail="Submission date must be between the assigned date and today.")
    if entry.submitted_on > assignment.due_date and not entry.reason:
        raise HTTPException(status_code=400, detail="A reason is required for a late submission.")


def summary(db, student_id, term, academic_year, include_withdrawn=False):
    today = school_today()
    query = db.query(ClassAssignment, AssignmentCompletion).join(AssignmentCompletion,
        AssignmentCompletion.assignment_id == ClassAssignment.assignment_id).filter(
        AssignmentCompletion.student_id == student_id, ClassAssignment.term == term,
        ClassAssignment.academic_year == academic_year)
    if not include_withdrawn:
        query = query.filter(ClassAssignment.is_withdrawn.is_(False))
    rows = query.order_by(ClassAssignment.due_date, ClassAssignment.assignment_id).all()
    counts = {key: 0 for key in ("PENDING", "MISSING", "SUBMITTED", "LATE", "EXCUSED")}
    due_count = completed_due = 0
    items, missing_titles = [], []
    for assignment, completion in rows:
        status = display_status(assignment, completion, today)
        items.append({"assignment": assignment, "status": completion.status, "display_status": status,
                      "submitted_on": completion.submitted_on, "reason": completion.reason})
        if assignment.is_withdrawn:
            continue
        counts[status] += 1
        if status == "MISSING":
            missing_titles.append(assignment.title)
        if assignment.due_date <= today and completion.status != "EXCUSED":
            due_count += 1
            if completion.status == "SUBMITTED":
                completed_due += 1
    return {"student_id": student_id, "term": term, "academic_year": academic_year, "as_of": today,
        "assignments": items, "counts": counts, "due_count": due_count, "completed_due_count": completed_due,
        "completion_rate": round(100 * completed_due / due_count, 1) if due_count else None,
        "guidance": ExpertSystemService.assignment_guidance(missing_titles)}


def notify_follow_up(db, student_ids, term, academic_year):
    """Run only after teacher saves. Reads derive status/guidance without side effects."""
    failures = []
    for student_id in set(student_ids):
        try:
            student = db.get(Student, student_id)
            if not student or archived(db, student_id):
                continue
            result = summary(db, student_id, term, academic_year)
            parents = {row.parent_user_id for row in db.query(ParentStudent).filter_by(student_id=student_id).all()}
            for parent_id in parents:
                key = f"assignment-followup:{parent_id}:{student_id}:{academic_year}:{term}"
                if result["counts"]["MISSING"]:
                    guidance = result["guidance"][0]["text"]
                    NotificationService.send_notification(db, parent_id, "ACADEMIC", "MEDIUM",
                        f"Assignment follow-up: {student.first_name}", guidance,
                        message_concise=f"{student.first_name} has {result['counts']['MISSING']} missing assignment(s) in {term}. Please review Assignments.",
                        suggested_action="Review missing work with the learner and coordinate a completion date with the teacher.",
                        student_id=student_id, source_ref=f"assignments:{student_id}:{term}:{academic_year}", dedup_key=key)
                else:
                    # Resolve an existing unread alert without creating a new notification.
                    existing = db.query(Notification).filter_by(recipient_user_id=parent_id, dedup_key=key, is_read=False).first()
                    if existing:
                        existing.title = f"Assignment follow-up resolved: {student.first_name}"
                        existing.message = "No assignments are currently missing for this period. Check Assignments for the latest recorded progress."
                        existing.priority = "LOW"
                        existing.suggested_action = None
                        db.commit()
        except Exception:
            db.rollback()
            logger.exception("Assignment notification delivery failed for learner %s", student_id)
            failures.append(student_id)
    return {"status": "retry_needed" if failures else "complete", "failed_student_ids": failures}
