"""Participant privacy, current write eligibility, and post-commit generic alerts."""
import logging
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import or_, and_, exists
from sqlalchemy.exc import IntegrityError
from app.models.messaging import Conversation, PrivateMessage
from app.models.student import Student, TeacherAssignment, ParentStudent
from app.models.user import User
from app.models.lifecycle import UserLifecycle
from app.models.notification import Notification, NotificationPreference
from app.services.lifecycle_service import active_students, active_users, archived

READ_ONLY = "Read-only history: current school relationships, account roles or learner status no longer permit replies."

def active_user(db, key, role):
    user, state = db.get(User, key), db.get(UserLifecycle, key)
    return bool(user and user.role == role and (state is None or state.is_active))

def assigned(db, user_id, student):
    return bool(db.query(TeacherAssignment).filter_by(teacher_user_id=user_id,
        grade_level=student.grade_level, stream=student.stream).first())

def linked(db, user_id, student_id):
    return bool(db.query(ParentStudent).filter_by(parent_user_id=user_id, student_id=student_id).first())

def writable(db, conversation):
    student = db.get(Student, conversation.student_id)
    return bool(student and not archived(db, student.student_id)
        and active_user(db, conversation.parent_user_id, "PARENT")
        and active_user(db, conversation.teacher_user_id, "TEACHER")
        and linked(db, conversation.parent_user_id, student.student_id)
        and assigned(db, conversation.teacher_user_id, student))

def require_writable(db, conversation):
    if not writable(db, conversation):
        raise HTTPException(status_code=403, detail=READ_ONLY)

def participant_filter(user_id):
    return or_(Conversation.parent_user_id == user_id, Conversation.teacher_user_id == user_id)

def get_conversation(db, actor, key, lock=False):
    query = db.query(Conversation).filter(Conversation.conversation_id == key, participant_filter(actor.user_id))
    if lock: query = query.with_for_update()
    row = query.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return row

def cursor_field(conversation, user_id):
    return "parent_read_id" if conversation.parent_user_id == user_id else "teacher_read_id"

def other_id(conversation, user_id):
    return conversation.teacher_user_id if conversation.parent_user_id == user_id else conversation.parent_user_id

def unread_query(db, conversation, user_id):
    return db.query(PrivateMessage).filter(PrivateMessage.conversation_id == conversation.conversation_id,
        PrivateMessage.sender_user_id != user_id,
        PrivateMessage.message_id > getattr(conversation, cursor_field(conversation, user_id)))

def describe(db, conversation, actor):
    student = db.get(Student, conversation.student_id)
    contact = db.get(User, other_id(conversation, actor.user_id))
    can_reply = writable(db, conversation)
    return {"conversation_id": conversation.conversation_id, "student_id": student.student_id,
        "student_name": f"{student.first_name} {student.last_name}", "contact_user_id": contact.user_id,
        "contact_name": contact.full_name, "can_reply": can_reply,
        "read_only_reason": None if can_reply else READ_ONLY,
        "unread_count": unread_query(db, conversation, actor.user_id).count(),
        "last_message_id": conversation.last_message_id,
        "peer_read_through_id": getattr(conversation, cursor_field(conversation, contact.user_id))}

def message_out(conversation, row, actor):
    peer_cursor = getattr(conversation, cursor_field(conversation, other_id(conversation, actor.user_id)))
    return {"message_id": row.message_id, "conversation_id": row.conversation_id,
        "sender_user_id": row.sender_user_id, "body": row.body, "sent_at": row.sent_at,
        "client_message_id": row.client_message_id, "is_mine": row.sender_user_id == actor.user_id,
        "is_read": row.sender_user_id == actor.user_id and row.message_id <= peer_cursor}

def learners(db, actor):
    query = db.query(Student).filter(active_students())
    if actor.role == "PARENT":
        query = query.filter(exists().where(ParentStudent.student_id == Student.student_id,
            ParentStudent.parent_user_id == actor.user_id))
    else:
        query = query.filter(exists().where(TeacherAssignment.teacher_user_id == actor.user_id,
            TeacherAssignment.grade_level == Student.grade_level, TeacherAssignment.stream == Student.stream))
    return [{"student_id": s.student_id, "name": f"{s.first_name} {s.last_name}",
        "grade_level": s.grade_level, "stream": s.stream} for s in query.order_by(Student.first_name, Student.student_id).all()]

def contacts(db, actor, student_id):
    student = db.query(Student).filter(Student.student_id == student_id, active_students()).first()
    if not student or not (linked(db, actor.user_id, student_id) if actor.role == "PARENT" else assigned(db, actor.user_id, student)):
        raise HTTPException(status_code=403, detail="You do not have current access to this learner's contacts.")
    query = db.query(User).filter(active_users())
    if actor.role == "PARENT":
        query = query.join(TeacherAssignment, TeacherAssignment.teacher_user_id == User.user_id).filter(
            User.role == "TEACHER", TeacherAssignment.grade_level == student.grade_level, TeacherAssignment.stream == student.stream)
    else:
        query = query.join(ParentStudent, ParentStudent.parent_user_id == User.user_id).filter(
            User.role == "PARENT", ParentStudent.student_id == student_id)
    return [{"user_id": u.user_id, "full_name": u.full_name, "role": u.role} for u in query.distinct().order_by(User.full_name, User.user_id).all()]

def start(db, actor, data):
    eligible = contacts(db, actor, data.student_id)
    if data.contact_user_id not in {u["user_id"] for u in eligible}:
        raise HTTPException(status_code=403, detail="Contact is not available for this learner.")
    key = dict(student_id=data.student_id,
        parent_user_id=actor.user_id if actor.role == "PARENT" else data.contact_user_id,
        teacher_user_id=actor.user_id if actor.role == "TEACHER" else data.contact_user_id)
    row = db.query(Conversation).filter_by(**key).first()
    if row is None:
        row = Conversation(**key)
        db.add(row)
        try: db.commit()
        except IntegrityError:
            db.rollback()
            row = db.query(Conversation).filter_by(**key).one()
    return describe(db, row, actor)

def notification_key(conversation_id, recipient):
    return f"messaging:{conversation_id}:{recipient}"

def deliver_notification(db, conversation_id, recipient):
    # Separate transaction after the message commit. The conversation lock serializes
    # alert creation/read clearing across both participants on MySQL.
    conversation = db.query(Conversation).filter_by(conversation_id=conversation_id).with_for_update().one()
    if not unread_query(db, conversation, recipient).first():
        db.commit()
        return
    prefs = db.query(NotificationPreference).filter_by(user_id=recipient).first()
    state = db.get(UserLifecycle, recipient)
    if (prefs and not prefs.notifications_enabled) or (state and not state.is_active):
        db.commit()
        return
    key = notification_key(conversation_id, recipient)
    alert = db.query(Notification).filter_by(recipient_user_id=recipient, dedup_key=key, is_read=False).first()
    if alert is None:
        alert = Notification(recipient_user_id=recipient, category="SYSTEM", priority="MEDIUM",
            title="New private message", message="You have a new message. Open Messages to read the conversation.",
            suggested_action="Open the Messages tab.", source_ref=f"messaging:{conversation_id}", dedup_key=key)
        db.add(alert)
    alert.created_at = datetime.utcnow()
    db.commit()

def notify_after_commit(db, conversation_id, recipient):
    try:
        deliver_notification(db, conversation_id, recipient)
        return {"status": "complete"}
    except Exception:
        db.rollback()
        logging.getLogger(__name__).exception("Private message saved; generic notification delivery failed")
        return {"status": "retry_needed"}

def send(db, actor, key, data):
    conversation = get_conversation(db, actor, key, lock=True)
    require_writable(db, conversation)
    recipient = other_id(conversation, actor.user_id)
    client_id = str(data.client_message_id)
    existing = db.query(PrivateMessage).filter_by(sender_user_id=actor.user_id, client_message_id=client_id).first()
    duplicate = existing is not None
    if existing:
        if existing.conversation_id != key or existing.body != data.body:
            raise HTTPException(status_code=409, detail="This send identifier was already used for different message content.")
        row = existing
        db.commit()
    else:
        row = PrivateMessage(conversation_id=key, sender_user_id=actor.user_id, client_message_id=client_id, body=data.body)
        db.add(row)
        try:
            db.flush()
            conversation.last_message_id = row.message_id
            db.commit()
        except IntegrityError:
            db.rollback()
            row = db.query(PrivateMessage).filter_by(sender_user_id=actor.user_id, client_message_id=client_id).first()
            if row is None or row.conversation_id != key or row.body != data.body:
                raise HTTPException(status_code=409, detail="Send identifier conflict.")
            duplicate = True
    result = message_out(conversation, row, actor)
    result["duplicate"] = duplicate
    result["notification_delivery"] = notify_after_commit(db, key, recipient)
    return result

def mark_read(db, actor, key, through):
    conversation = get_conversation(db, actor, key, lock=True)
    if not db.query(PrivateMessage).filter_by(conversation_id=key, message_id=through).first():
        raise HTTPException(status_code=400, detail="Read cursor must reference a message in this conversation.")
    field = cursor_field(conversation, actor.user_id)
    setattr(conversation, field, max(getattr(conversation, field), through))
    # Session autoflush is disabled; update before checking remaining unread messages.
    db.flush()
    if not unread_query(db, conversation, actor.user_id).first():
        alerts = db.query(Notification).filter_by(recipient_user_id=actor.user_id,
            dedup_key=notification_key(key, actor.user_id), is_read=False).all()
        for alert in alerts: alert.is_read, alert.read_at = True, datetime.utcnow()
    db.commit()
    return describe(db, conversation, actor)
