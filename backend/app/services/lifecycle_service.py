"""Access, lifecycle and correction history shared by admin and teacher routes."""
import json
from fastapi import HTTPException
from sqlalchemy import exists, inspect
from app.models.lifecycle import UserLifecycle, StudentLifecycle, RecordChange
from app.models.student import Student
from app.models.user import User


def active_students():
    return ~exists().where(StudentLifecycle.student_id == Student.student_id,
                           StudentLifecycle.is_archived.is_(True))


def active_users():
    return ~exists().where(UserLifecycle.user_id == User.user_id,
                           UserLifecycle.is_active.is_(False))


def user_state(db, user_id):
    row = db.get(UserLifecycle, user_id)
    if row is None:
        row = UserLifecycle(user_id=user_id, is_active=True, token_version=0)
        db.add(row)
        db.flush()
    return row


def archived(db, student_id):
    row = db.get(StudentLifecycle, student_id)
    return bool(row and row.is_archived)


def require_active_student(db, student):
    if archived(db, student.student_id):
        raise HTTPException(status_code=403, detail="This learner is archived. Restore the learner before making changes.")


def snapshot(row):
    return {column.key: getattr(row, column.key) for column in inspect(row).mapper.column_attrs
            if column.key != "password_hash"}


def record_change(db, actor, row, action, before=None):
    identity = inspect(row).identity
    db.add(RecordChange(actor_user_id=actor.user_id, entity_type=row.__tablename__,
        entity_id=identity[0], action=action,
        before_json=json.dumps(before, default=str) if before is not None else None,
        after_json=json.dumps(snapshot(row), default=str) if action != "delete" else None))
