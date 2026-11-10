"""
Adaptive Notification Service.

Determines notification priority, constructive tone, and appropriate detail level
based on:
    - Learner risk indicators and continuous probability
    - CBC-aligned expert system recommendations
    - Attendance and engagement patterns
    - Recipient communication preferences (Detailed vs. Concise)
    - Anti-flood deduplication to prevent repetitive notifications on recalculation
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.analytics import Recommendation, StudentAnalytics
from app.models.notification import Notification, NotificationPreference
from app.models.student import ParentStudent, Student, TeacherAssignment
from app.models.user import User
from app.models.lifecycle import UserLifecycle

logger = logging.getLogger(__name__)


class NotificationService:
    """
    In-app adaptive notification engine.
    """

    @staticmethod
    def get_or_create_preferences(db: Session, user_id: int) -> NotificationPreference:
        """
        Retrieve or initialize default communication preferences for a user.
        """
        prefs = (
            db.query(NotificationPreference)
            .filter(NotificationPreference.user_id == user_id)
            .first()
        )
        if not prefs:
            prefs = NotificationPreference(
                user_id=user_id,
                notifications_enabled=True,
                academic_updates=True,
                attendance_updates=True,
                behaviour_updates=True,
                support_updates=True,
                communication_style="DETAILED",
                updated_at=datetime.utcnow(),
            )
            db.add(prefs)
            db.commit()
            db.refresh(prefs)
        return prefs

    @staticmethod
    def send_notification(
        db: Session,
        recipient_user_id: int,
        category: str,
        priority: str,
        title: str,
        message_detailed: str,
        message_concise: Optional[str] = None,
        suggested_action: Optional[str] = None,
        student_id: Optional[int] = None,
        source_ref: Optional[str] = None,
        dedup_key: Optional[str] = None,
    ) -> Optional[Notification]:
        """
        Deliver a notification respecting recipient communication preferences
        and deduplication rules.

        Critical/High priority notifications bypass optional category disablement,
        ensuring vital school advisories are never silently suppressed.
        """
        lifecycle = db.get(UserLifecycle, recipient_user_id)
        if lifecycle and not lifecycle.is_active:
            return None
        priority_upper = priority.upper()
        category_upper = category.upper()

        prefs = NotificationService.get_or_create_preferences(db, recipient_user_id)

        # Check global toggle (High priority notifications always delivered)
        if not prefs.notifications_enabled and priority_upper != "HIGH":
            logger.info("Notification suppressed for user %s: notifications disabled", recipient_user_id)
            return None

        # Check category preferences (High priority notifications bypass category disablement)
        if priority_upper != "HIGH":
            if category_upper == "ACADEMIC" and not prefs.academic_updates:
                return None
            if category_upper == "ATTENDANCE" and not prefs.attendance_updates:
                return None
            if category_upper == "BEHAVIOUR" and not prefs.behaviour_updates:
                return None
            if category_upper == "SUPPORT" and not prefs.support_updates:
                return None

        # Select message style
        if prefs.communication_style == "CONCISE" and message_concise:
            message = message_concise
        else:
            message = message_detailed

        # Deduplication check: if an unread notification or identical recent alert exists with dedup_key
        if dedup_key:
            existing = (
                db.query(Notification)
                .filter(
                    Notification.recipient_user_id == recipient_user_id,
                    Notification.dedup_key == dedup_key,
                )
                .order_by(Notification.created_at.desc())
                .first()
            )
            if existing:
                # If still unread, update message and timestamp rather than spamming a duplicate
                if not existing.is_read:
                    existing.priority = priority_upper
                    existing.category = category_upper
                    existing.source_ref = source_ref
                    existing.title = title
                    existing.message = message
                    existing.suggested_action = suggested_action
                    existing.created_at = datetime.utcnow()
                    db.commit()
                    db.refresh(existing)
                    return existing
                # If read within the last 24 hours, do not re-alert for the exact same event
                elif (existing.read_at or existing.created_at) and (existing.read_at or existing.created_at) > datetime.utcnow() - timedelta(hours=24):
                    logger.info("Skipping duplicate notification for key %s (already sent within 24h)", dedup_key)
                    return existing

        notification = Notification(
            recipient_user_id=recipient_user_id,
            student_id=student_id,
            category=category_upper,
            priority=priority_upper,
            title=title,
            message=message,
            suggested_action=suggested_action,
            created_at=datetime.utcnow(),
            is_read=False,
            source_ref=source_ref,
            dedup_key=dedup_key,
        )

        db.add(notification)
        db.commit()
        db.refresh(notification)
        return notification

    @staticmethod
    def dispatch_analytics_notifications(
        db: Session,
        student: Student,
        analytics: StudentAnalytics,
        recommendations: List[Recommendation],
        term: str,
        academic_year: str,
        absences_count: int | float = 0,
        cohort_percentile: Optional[float] = None,
    ) -> List[Notification]:
        """
        Generate and deliver role-tailored notifications to linked parents
        and assigned class teachers following an analytics evaluation.
        """
        created: List[Notification] = []

        support_status = analytics.support_status
        prob = analytics.support_probability or 0.0
        avg = analytics.overall_average or 0.0

        # 1. Linked Parents
        parent_links = (
            db.query(ParentStudent)
            .filter(ParentStudent.student_id == student.student_id)
            .all()
        )

        for link in parent_links:
            parent_id = link.parent_user_id

            # Analytics Status Notification
            if support_status == "Targeted Support Recommended":
                notif = NotificationService.send_notification(
                    db=db,
                    recipient_user_id=parent_id,
                    student_id=student.student_id,
                    category="SUPPORT",
                    priority="HIGH",
                    title=f"Learning Support Advisory: {student.first_name}",
                    message_detailed=(
                        f"Early learner indicators for {student.first_name} suggest that targeted learning "
                        f"support would be beneficial in {term} (estimated advisory support probability: {prob:.1%}). "
                        f"We recommend coordinating with the subject teacher to establish structured home practice "
                        f"and remedial focus areas."
                    ),
                    message_concise=(
                        f"Targeted learning support recommended for {student.first_name} in {term} "
                        f"(support probability: {prob:.1%}). Please coordinate with the school for guidance."
                    ),
                    suggested_action=(
                        f"Schedule a consultation with {student.first_name}'s class teacher to review learning targets."
                    ),
                    source_ref=f"analytics:{analytics.analytics_id}",
                    dedup_key=f"parent:{parent_id}:student:{student.student_id}:{academic_year}:{term}:status:{support_status}",
                )
                if notif:
                    created.append(notif)

            elif support_status == "Monitoring Suggested":
                notif = NotificationService.send_notification(
                    db=db,
                    recipient_user_id=parent_id,
                    student_id=student.student_id,
                    category="ACADEMIC",
                    priority="MEDIUM",
                    title=f"Progress Advisory: {student.first_name}",
                    message_detailed=(
                        f"{student.first_name}'s academic indicators in {term} suggest close monitoring "
                        f"(overall average: {avg:.1f}%). Regular check-ins on daily assignments and conceptual "
                        f"revision will help keep progress steady."
                    ),
                    message_concise=(
                        f"Close monitoring suggested for {student.first_name} in {term} (average: {avg:.1f}%)."
                    ),
                    suggested_action=(
                        f"Review weekly homework and check in with {student.first_name} on challenging topics."
                    ),
                    source_ref=f"analytics:{analytics.analytics_id}",
                    dedup_key=f"parent:{parent_id}:student:{student.student_id}:{academic_year}:{term}:status:{support_status}",
                )
                if notif:
                    created.append(notif)

            else:  # On Track
                pct_str = f" (cohort percentile: {cohort_percentile:.0f}%)" if cohort_percentile is not None else ""
                notif = NotificationService.send_notification(
                    db=db,
                    recipient_user_id=parent_id,
                    student_id=student.student_id,
                    category="ACADEMIC",
                    priority="LOW",
                    title=f"Commendable Progress: {student.first_name}",
                    message_detailed=(
                        f"{student.first_name} is performing commendably on track in {term} with an overall average of "
                        f"{avg:.1f}%{pct_str}. Continue positive reinforcement and encouraging curiosity at home."
                    ),
                    message_concise=(
                        f"Great news! {student.first_name} is on track in {term} with an overall average of {avg:.1f}%."
                    ),
                    suggested_action=(
                        f"Acknowledge and celebrate {student.first_name}'s effort and positive study habits."
                    ),
                    source_ref=f"analytics:{analytics.analytics_id}",
                    dedup_key=f"parent:{parent_id}:student:{student.student_id}:{academic_year}:{term}:status:{support_status}",
                )
                if notif:
                    created.append(notif)

            # Attendance Notification (if absences >= 3)
            if absences_count >= 3:
                notif_attend = NotificationService.send_notification(
                    db=db,
                    recipient_user_id=parent_id,
                    student_id=student.student_id,
                    category="ATTENDANCE",
                    priority="HIGH" if absences_count >= 5 else "MEDIUM",
                    title=f"Attendance Advisory: {student.first_name}",
                    message_detailed=(
                        f"{student.first_name} has accumulated {int(absences_count)} school absences to date in {term}. "
                        f"Regular daily attendance is essential to prevent instructional gaps."
                    ),
                    message_concise=(
                        f"{student.first_name} has {int(absences_count)} school absences in {term}. Daily attendance is advised."
                    ),
                    suggested_action=(
                        f"Ensure regular school attendance and contact the school if absences are due to medical reasons."
                    ),
                    source_ref=f"attendance:{student.student_id}:{term}:{academic_year}",
                    dedup_key=f"parent:{parent_id}:student:{student.student_id}:{academic_year}:{term}:absences:{int(absences_count)}",
                )
                if notif_attend:
                    created.append(notif_attend)

            for rec in recommendations:
                if rec.rule_code == "BEHAV_ATTENTION_REQUIRED":
                    notification = NotificationService.send_notification(
                        db=db, recipient_user_id=parent_id, student_id=student.student_id,
                        category="BEHAVIOUR", priority="MEDIUM",
                        title=f"Classroom Guidance: {student.first_name}",
                        message_detailed=rec.recommendation_text,
                        message_concise=f"Classroom habits need support for {student.first_name}. Review teacher guidance.",
                        suggested_action="Review the guidance and discuss classroom routines with the teacher.",
                        source_ref=f"recommendation:{rec.recommendation_id}",
                        dedup_key=f"parent:{parent_id}:student:{student.student_id}:{academic_year}:{term}:behaviour",
                    )
                    if notification:
                        created.append(notification)

        # 2. Assigned Teachers
        assignments = (
            db.query(TeacherAssignment)
            .filter(
                TeacherAssignment.grade_level == student.grade_level,
                TeacherAssignment.stream == student.stream,
            )
            .all()
        )
        unique_teacher_ids = {a.teacher_user_id for a in assignments}

        for teacher_id in unique_teacher_ids:
            if support_status == "Targeted Support Recommended":
                notif = NotificationService.send_notification(
                    db=db,
                    recipient_user_id=teacher_id,
                    student_id=student.student_id,
                    category="SUPPORT",
                    priority="HIGH",
                    title=f"Targeted Support Flag: {student.first_name} {student.last_name}",
                    message_detailed=(
                        f"Learner {student.first_name} {student.last_name} ({student.admission_number}) in "
                        f"{student.grade_level} {student.stream or ''} has an advisory support probability of "
                        f"{prob:.1%}. Review continuous assessment records and consider targeted classroom check-ins."
                    ),
                    message_concise=(
                        f"Targeted support flagged for {student.first_name} {student.last_name} "
                        f"({prob:.1%} support probability)."
                    ),
                    suggested_action=(
                        f"Review subject breakdown and coordinate with the learner's parent for tailored support."
                    ),
                    source_ref=f"analytics:{analytics.analytics_id}",
                    dedup_key=f"teacher:{teacher_id}:student:{student.student_id}:{academic_year}:{term}:status:{support_status}",
                )
                if notif:
                    created.append(notif)
            elif support_status == "Monitoring Suggested":
                notif = NotificationService.send_notification(
                    db=db,
                    recipient_user_id=teacher_id,
                    student_id=student.student_id,
                    category="ACADEMIC",
                    priority="MEDIUM",
                    title=f"Monitoring Advisory: {student.first_name} {student.last_name}",
                    message_detailed=(
                        f"Learner {student.first_name} {student.last_name} ({student.admission_number}) has an overall "
                        f"average of {avg:.1f}% in {term}. Monitor class engagement and homework submission."
                    ),
                    message_concise=(
                        f"Monitoring advisory for {student.first_name} {student.last_name} (average: {avg:.1f}%)."
                    ),
                    suggested_action=(
                        f"Observe classroom concept grasp and formative exercise completion."
                    ),
                    source_ref=f"analytics:{analytics.analytics_id}",
                    dedup_key=f"teacher:{teacher_id}:student:{student.student_id}:{academic_year}:{term}:status:{support_status}",
                )
                if notif:
                    created.append(notif)

        return created
