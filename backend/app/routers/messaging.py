"""Private messaging: no administrator or non-participant content access."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import require_role
from app.models.messaging import Conversation, PrivateMessage
from app.schemas.messaging import StartConversation, SendMessage, ReadMessages
from app.services import messaging_service as service

router = APIRouter(prefix="/messaging", tags=["Private Messaging"])
participant = require_role(["TEACHER", "PARENT"])

@router.get("/learners")
def learners(actor=Depends(participant), db: Session=Depends(get_db)):
    return service.learners(db, actor)

@router.get("/contacts")
def contacts(student_id: int = Query(gt=0), actor=Depends(participant), db: Session=Depends(get_db)):
    return service.contacts(db, actor, student_id)

@router.get("/conversations")
def conversations(limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0),
    actor=Depends(participant), db: Session=Depends(get_db)):
    query = db.query(Conversation).filter(service.participant_filter(actor.user_id))
    rows = query.order_by(Conversation.last_message_id.desc(), Conversation.conversation_id.desc()).offset(offset).limit(limit+1).all()
    unread = db.query(func.count(PrivateMessage.message_id)).join(Conversation,
        Conversation.conversation_id == PrivateMessage.conversation_id).filter(service.participant_filter(actor.user_id),
        PrivateMessage.sender_user_id != actor.user_id,
        or_(and_(Conversation.parent_user_id == actor.user_id, PrivateMessage.message_id > Conversation.parent_read_id),
            and_(Conversation.teacher_user_id == actor.user_id, PrivateMessage.message_id > Conversation.teacher_read_id))).scalar()
    return {"items": [service.describe(db, row, actor) for row in rows[:limit]],
        "has_more": len(rows)>limit, "offset": offset, "unread_total": unread}

@router.post("/conversations")
def start(data: StartConversation, actor=Depends(participant), db: Session=Depends(get_db)):
    return service.start(db, actor, data)

@router.get("/conversations/{conversation_id}/messages")
def messages(conversation_id: int, limit: int = Query(50, ge=1, le=100),
    before_id: int | None = Query(None, gt=0), after_id: int | None = Query(None, gt=0),
    actor=Depends(participant), db: Session=Depends(get_db)):
    conversation = service.get_conversation(db, actor, conversation_id)
    if before_id is not None and after_id is not None:
        raise HTTPException(status_code=400, detail="Use before_id or after_id, not both.")
    query = db.query(PrivateMessage).filter_by(conversation_id=conversation_id)
    if after_id is not None:
        rows = query.filter(PrivateMessage.message_id > after_id).order_by(PrivateMessage.message_id).limit(limit+1).all()
    else:
        if before_id is not None: query = query.filter(PrivateMessage.message_id < before_id)
        rows = query.order_by(PrivateMessage.message_id.desc()).limit(limit+1).all()
    has_more = len(rows)>limit
    rows = rows[:limit]
    if after_id is None: rows.reverse()
    has_older = bool(rows and db.query(PrivateMessage).filter(PrivateMessage.conversation_id == conversation_id,
        PrivateMessage.message_id < rows[0].message_id).first())
    return {"conversation": service.describe(db, conversation, actor),
        "items": [service.message_out(conversation, row, actor) for row in rows],
        "has_older": has_older, "has_more": has_more}

@router.post("/conversations/{conversation_id}/messages")
def send(conversation_id: int, data: SendMessage, actor=Depends(participant), db: Session=Depends(get_db)):
    return service.send(db, actor, conversation_id, data)

@router.post("/conversations/{conversation_id}/read")
def read(conversation_id: int, data: ReadMessages, actor=Depends(participant), db: Session=Depends(get_db)):
    return service.mark_read(db, actor, conversation_id, data.through_message_id)
