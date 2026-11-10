"""Explicit, additive fictional private-message examples; no automatic school messages."""
from uuid import uuid5, NAMESPACE_URL
from sqlalchemy import select
from app.models.messaging import Conversation, PrivateMessage
from app.models.student import Student
from app.models.user import User
from app.schemas.messaging import StartConversation, SendMessage
from app.services import messaging_service as service

def seed_messaging(db):
    users={role:db.scalar(select(User).filter_by(email_or_username=f'demo.{role}')) for role in ['parent','teacher']}
    student=db.scalar(select(Student).filter_by(admission_number='DEMO-001'))
    if any(not user or user.full_name != f'Fictional Demo {role.title()}' or user.role != role.upper() for role,user in users.items()) or not student or student.first_name!='Amina' or student.last_name!='Demo' or student.grade_level!='Grade 7' or student.stream!='Demo East':
        raise RuntimeError('Original fictional demo accounts and Amina fixture required; no messages written.')
    # Preserve an existing real demonstration conversation; do not inject examples later.
    existing=db.scalar(select(Conversation).filter_by(student_id=student.student_id,parent_user_id=users['parent'].user_id,teacher_user_id=users['teacher'].user_id))
    if existing:return existing.conversation_id
    data=service.start(db,users['parent'],StartConversation(student_id=student.student_id,contact_user_id=users['teacher'].user_id))
    key=data['conversation_id']
    for role,body in [('parent','Fictional demo: could we discuss Amina’s fraction practice?'),('teacher','Fictional demo: please review the recorded competency evidence together. We can agree on a short practice activity.')]:
        service.send(db,users[role],key,SendMessage(body=body,client_message_id=uuid5(NAMESPACE_URL,f'ipd-fictional-message:{key}:{role}')))
    return key
