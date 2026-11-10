"""
Notification Router.

Exposes endpoints for:
    - Listing notifications for the current authenticated user
    - Viewing unread notification counts
    - Marking individual or all notifications as read
    - Retrieving and updating user communication preferences
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.notification import Notification, NotificationPreference
from app.models.student import Student
from app.models.user import User
from app.schemas.notification import (
    NotificationOut,
    NotificationPreferenceOut,
    NotificationPreferenceUpdate,
    UnreadCountOut,
)
from app.services.notification_service import NotificationService

router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"],
)


@router.get("", response_model=List[NotificationOut])
def list_notifications(
    unread_only: bool = Query(False, description="Filter for unread notifications only"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of notifications to return"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List notifications addressed to the current authenticated user.
    Strictly scoped to the user's recipient ID.
    """
    query = (
        db.query(
            Notification,
            Student.first_name,
            Student.last_name,
        )
        .outerjoin(Student, Notification.student_id == Student.student_id)
        .filter(Notification.recipient_user_id == current_user.user_id)
    )

    if unread_only:
        query = query.filter(Notification.is_read.is_(False))

    results = query.order_by(Notification.created_at.desc()).limit(limit).all()

    out = []
    for notif, first_name, last_name in results:
        student_name = f"{first_name} {last_name}".strip() if first_name else None
        item = NotificationOut(
            notification_id=notif.notification_id,
            recipient_user_id=notif.recipient_user_id,
            student_id=notif.student_id,
            student_name=student_name,
            category=notif.category,
            priority=notif.priority,
            title=notif.title,
            message=notif.message,
            suggested_action=notif.suggested_action,
            created_at=notif.created_at,
            is_read=notif.is_read,
            read_at=notif.read_at,
            source_ref=notif.source_ref,
        )
        out.append(item)

    return out


@router.get("/unread-count", response_model=UnreadCountOut)
def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return count of unread notifications for the current user.
    """
    count = (
        db.query(Notification)
        .filter(
            Notification.recipient_user_id == current_user.user_id,
            Notification.is_read.is_(False),
        )
        .count()
    )
    return UnreadCountOut(unread_count=count)


@router.patch("/{notification_id}/read", response_model=NotificationOut)
def mark_notification_as_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Mark an individual notification as read.
    Enforces strict ownership: users can only modify their own notifications.
    """
    notif = (
        db.query(Notification)
        .filter(Notification.notification_id == notification_id)
        .first()
    )

    if not notif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification {notification_id} not found.",
        )

    if notif.recipient_user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to modify this notification.",
        )

    if not notif.is_read:
        notif.is_read = True
        notif.read_at = datetime.utcnow()
        db.commit()
        db.refresh(notif)

    student_name = None
    if notif.student_id:
        student = db.query(Student).filter(Student.student_id == notif.student_id).first()
        if student:
            student_name = f"{student.first_name} {student.last_name}"

    return NotificationOut(
        notification_id=notif.notification_id,
        recipient_user_id=notif.recipient_user_id,
        student_id=notif.student_id,
        student_name=student_name,
        category=notif.category,
        priority=notif.priority,
        title=notif.title,
        message=notif.message,
        suggested_action=notif.suggested_action,
        created_at=notif.created_at,
        is_read=notif.is_read,
        read_at=notif.read_at,
        source_ref=notif.source_ref,
    )


@router.patch("/mark-all-read")
def mark_all_notifications_as_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Mark all unread notifications for the current user as read.
    """
    now = datetime.utcnow()
    updated_count = (
        db.query(Notification)
        .filter(
            Notification.recipient_user_id == current_user.user_id,
            Notification.is_read.is_(False),
        )
        .update(
            {"is_read": True, "read_at": now},
            synchronize_session=False,
        )
    )
    db.commit()
    return {
        "message": "All notifications marked as read.",
        "marked_count": updated_count,
    }


@router.get("/preferences", response_model=NotificationPreferenceOut)
def get_preferences(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve notification preferences for the current user.
    """
    prefs = NotificationService.get_or_create_preferences(db, current_user.user_id)
    return NotificationPreferenceOut.model_validate(prefs)


@router.put("/preferences", response_model=NotificationPreferenceOut)
def update_preferences(
    payload: NotificationPreferenceUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update communication preferences for the current user.
    """
    prefs = NotificationService.get_or_create_preferences(db, current_user.user_id)

    if payload.notifications_enabled is not None:
        prefs.notifications_enabled = payload.notifications_enabled
    if payload.academic_updates is not None:
        prefs.academic_updates = payload.academic_updates
    if payload.attendance_updates is not None:
        prefs.attendance_updates = payload.attendance_updates
    if payload.behaviour_updates is not None:
        prefs.behaviour_updates = payload.behaviour_updates
    if payload.support_updates is not None:
        prefs.support_updates = payload.support_updates
    if payload.communication_style is not None:
        style_upper = payload.communication_style.upper().strip()
        if style_upper not in ["DETAILED", "CONCISE"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Communication style must be either 'DETAILED' or 'CONCISE'.",
            )
        prefs.communication_style = style_upper

    prefs.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(prefs)

    return NotificationPreferenceOut.model_validate(prefs)
