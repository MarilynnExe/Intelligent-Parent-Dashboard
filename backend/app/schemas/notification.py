"""
Pydantic Schemas for Adaptive Notifications and Preferences.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    notification_id: int
    recipient_user_id: int
    student_id: Optional[int] = None
    student_name: Optional[str] = None
    category: str
    priority: str
    title: str
    message: str
    suggested_action: Optional[str] = None
    created_at: datetime
    is_read: bool
    read_at: Optional[datetime] = None
    source_ref: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UnreadCountOut(BaseModel):
    unread_count: int


class NotificationPreferenceOut(BaseModel):
    user_id: int
    notifications_enabled: bool
    academic_updates: bool
    attendance_updates: bool
    behaviour_updates: bool
    support_updates: bool
    communication_style: str

    model_config = ConfigDict(from_attributes=True)


class NotificationPreferenceUpdate(BaseModel):
    notifications_enabled: Optional[bool] = None
    academic_updates: Optional[bool] = None
    attendance_updates: Optional[bool] = None
    behaviour_updates: Optional[bool] = None
    support_updates: Optional[bool] = None
    communication_style: Optional[str] = None
