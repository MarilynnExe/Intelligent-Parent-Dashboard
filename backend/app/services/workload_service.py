"""
Teacher Workload Monitoring and Balancing Service.

Provides administrative visibility into teacher assignment distribution, learner
support density, and instructional load disparities.

Key Principles:
    1. Grounded in Existing Database Records:
       - Uses teacher assignments, student class enrollments, analytics support status,
         and in-app notification registers.
       - Distinguishes class cohort management (distinct physical classes) from subject-class
         preparations (multiple subject curricula taught across cohorts).
    2. Transparent Heuristic Scoring:
       - Configurable composite workload index combining learner volume, class cohorts,
         subject-class preparations, and intensive intervention density.
       - Unread notifications are maintained for operational context only and do NOT
         affect the numerical workload score.
       - Clearly documented as an administrative operational heuristic, NOT a clinical
         or scientifically validated burnout metric.
    3. Prudent, Actionable Administrative Recommendations:
       - Subject-aware matching: Suggests reassignments only when teacher subject
         specialization is established, or clearly identifies when qualification
         verification is required by the administrator.
       - Advisory only: Never automatically alters teacher assignments or permissions.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models.analytics import StudentAnalytics
from app.models.notification import Notification
from app.models.student import Student, TeacherAssignment
from app.models.user import User
from app.services.lifecycle_service import active_students, active_users
from app.schemas.workload import (
    TeacherWorkloadItem,
    TeacherWorkloadReportOut,
    TeacherWorkloadSummary,
    WorkloadBalancingRecommendation,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configurable Workload Weights and Thresholds
# ---------------------------------------------------------------------------
# Refined formula distinguishes physical class cohorts from distinct subject preparations:
# Single-subject assignment in 1 class receives (1 x 3.0) + (1 x 2.0) = 5.0 points (identical baseline).
# Multiple subjects within 1 class receive fair credit for each distinct curriculum preparation (+2.0 pts).
WEIGHT_LEARNER: float = 1.0               # Base point per assigned learner
WEIGHT_CLASS: float = 3.0                 # Points per distinct physical class cohort (registration, classroom admin)
WEIGHT_SUBJECT_PREPARATION: float = 2.0   # Points per distinct subject-class preparation (curriculum, assessments)
WEIGHT_TARGETED_SUPPORT: float = 3.0      # Points per learner requiring intensive early intervention
WEIGHT_MONITORING: float = 1.5            # Points per learner requiring periodic monitoring

HIGH_WORKLOAD_THRESHOLD: float = 60.0
MODERATE_WORKLOAD_THRESHOLD: float = 30.0

SCORING_METHODOLOGY_DISCLAIMER: str = (
    "Workload Score = (Assigned Learners x 1.0) + (Class Cohorts x 3.0) + "
    "(Subject-Class Preparations x 2.0) + (Targeted Support Learners x 3.0) + (Monitoring Learners x 1.5). "
    "This score is an administrative operational heuristic and system-defined triage indicator "
    "established for administrative resource allocation. Unread notifications and operational alerts are displayed "
    "for administrative context only and do not factor into the score. This score is NOT a clinically or "
    "scientifically validated measure of teacher burnout or official Ministry of Education workload standard."
)


class WorkloadService:
    """
    Computes individual teacher workloads and generates high-level
    workload balancing reports for administrators.
    """

    @staticmethod
    def calculate_teacher_workload(
        db: Session,
        teacher: User,
    ) -> TeacherWorkloadItem:
        """
        Calculates the workload metrics for an individual teacher based on existing
        assignments, enrolled learners in their classes, and learner support statuses.
        """
        # 1. Fetch teacher assignments
        assignments = (
            db.query(TeacherAssignment)
            .filter(TeacherAssignment.teacher_user_id == teacher.user_id)
            .all()
        )

        if not assignments:
            # Teacher has no active assignments
            unread_count, high_unread_count = WorkloadService._get_teacher_notifications(db, teacher.user_id)
            return TeacherWorkloadItem(
                teacher_user_id=teacher.user_id,
                teacher_name=teacher.full_name,
                email_or_username=teacher.email_or_username,
                assigned_classes=[],
                assigned_subjects=[],
                total_classes_count=0,
                subject_assignments_count=0,
                assigned_learners_count=0,
                targeted_support_count=0,
                monitoring_count=0,
                on_track_count=0,
                unassessed_learners_count=0,
                unread_notifications_count=unread_count,
                high_priority_notifications_count=high_unread_count,
                workload_score=0.0,
                workload_status="UNASSIGNED",
                workload_label="No Active Assignments",
                explanation="System-defined status: Teacher currently has no assigned streams or classes. Full operational capacity available for new allocations.",
            )

        # 2. Extract distinct physical classes (grade_level, stream) and distinct subjects
        class_pairs: Set[Tuple[str, str]] = {(a.grade_level, a.stream) for a in assignments}
        assigned_classes = sorted([f"{gl} {st}" for gl, st in class_pairs])
        assigned_subjects = sorted(list({a.subject_name for a in assignments}))
        total_classes_count = len(class_pairs)
        subject_assignments_count = len(assignments)

        # 3. Query distinct students enrolled in these classes
        class_filters = [
            and_(Student.grade_level == gl, Student.stream == st)
            for gl, st in class_pairs
        ]
        students = db.query(Student).filter(active_students(), or_(*class_filters)).all() if class_filters else []
        assigned_learners_count = len(students)

        # 4. Determine support status breakdown for assigned learners from StudentAnalytics
        student_ids = [s.student_id for s in students]
        latest_analytics_map: Dict[int, StudentAnalytics] = {}

        if student_ids:
            analytics_records = (
                db.query(StudentAnalytics)
                .filter(StudentAnalytics.student_id.in_(student_ids))
                .order_by(StudentAnalytics.calculated_at.desc(), StudentAnalytics.analytics_id.desc())
                .all()
            )
            for a in analytics_records:
                if a.student_id not in latest_analytics_map:
                    latest_analytics_map[a.student_id] = a

        targeted_support_count = 0
        monitoring_count = 0
        on_track_count = 0
        unassessed_learners_count = 0

        for s in students:
            analytics = latest_analytics_map.get(s.student_id)
            if not analytics or not analytics.support_status:
                unassessed_learners_count += 1
            elif analytics.support_status == "Targeted Support Recommended":
                targeted_support_count += 1
            elif analytics.support_status == "Monitoring Suggested":
                monitoring_count += 1
            elif analytics.support_status == "On Track":
                on_track_count += 1
            else:
                unassessed_learners_count += 1

        # 5. Query unread and high-priority notifications for the teacher
        # NOTE: Unread notifications provide operational situational awareness and do NOT alter the workload score.
        unread_count, high_unread_count = WorkloadService._get_teacher_notifications(db, teacher.user_id)

        # 6. Compute composite workload score and classification
        workload_score = (
            (assigned_learners_count * WEIGHT_LEARNER)
            + (total_classes_count * WEIGHT_CLASS)
            + (subject_assignments_count * WEIGHT_SUBJECT_PREPARATION)
            + (targeted_support_count * WEIGHT_TARGETED_SUPPORT)
            + (monitoring_count * WEIGHT_MONITORING)
        )

        if workload_score >= HIGH_WORKLOAD_THRESHOLD or assigned_learners_count >= 40 or targeted_support_count >= 8:
            workload_status = "HIGH"
            workload_label = "High Workload"
            explanation = (
                f"System-defined operational status: High instructional volume managing {assigned_learners_count} learners "
                f"across {total_classes_count} class cohort(s) and {subject_assignments_count} subject preparation(s), with "
                f"{targeted_support_count} requiring targeted early intervention (Score: {workload_score:.1f}). "
                f"Represents potential administrative bottleneck; not a validated burnout metric."
            )
        elif workload_score >= MODERATE_WORKLOAD_THRESHOLD:
            workload_status = "MODERATE"
            workload_label = "Moderate Workload"
            explanation = (
                f"System-defined operational status: Balanced assignment load managing {assigned_learners_count} learners "
                f"across {total_classes_count} class cohort(s) and {subject_assignments_count} subject preparation(s) "
                f"(Score: {workload_score:.1f}). Assignment load is within typical operational parameters."
            )
        else:
            workload_status = "LOW"
            workload_label = "Available Capacity"
            explanation = (
                f"System-defined operational status: Lighter assignment load ({assigned_learners_count} learners across "
                f"{total_classes_count} class cohort(s), {subject_assignments_count} subject preparation(s); Score: {workload_score:.1f}). "
                f"Operational capacity is available for additional assignments or co-teaching."
            )

        return TeacherWorkloadItem(
            teacher_user_id=teacher.user_id,
            teacher_name=teacher.full_name,
            email_or_username=teacher.email_or_username,
            assigned_classes=assigned_classes,
            assigned_subjects=assigned_subjects,
            total_classes_count=total_classes_count,
            subject_assignments_count=subject_assignments_count,
            assigned_learners_count=assigned_learners_count,
            targeted_support_count=targeted_support_count,
            monitoring_count=monitoring_count,
            on_track_count=on_track_count,
            unassessed_learners_count=unassessed_learners_count,
            unread_notifications_count=unread_count,
            high_priority_notifications_count=high_unread_count,
            workload_score=round(workload_score, 1),
            workload_status=workload_status,
            workload_label=workload_label,
            explanation=explanation,
        )

    @staticmethod
    def get_all_teachers_workload_report(db: Session) -> TeacherWorkloadReportOut:
        """
        Retrieves workload metrics across all registered teachers, evaluates system-level
        workload disparities, and produces administrative balancing recommendations.
        """
        teachers = (
            db.query(User)
            .filter(User.role == "TEACHER", active_users())
            .order_by(User.full_name.asc())
            .all()
        )

        teacher_items = [WorkloadService.calculate_teacher_workload(db, t) for t in teachers]

        # Summary statistics
        total_teachers = len(teachers)
        active_teachers_count = sum(1 for t in teacher_items if t.workload_status != "UNASSIGNED")
        unassigned_teachers_count = sum(1 for t in teacher_items if t.workload_status == "UNASSIGNED")
        high_workload_count = sum(1 for t in teacher_items if t.workload_status == "HIGH")
        moderate_workload_count = sum(1 for t in teacher_items if t.workload_status == "MODERATE")
        low_workload_count = sum(1 for t in teacher_items if t.workload_status == "LOW")

        total_learners_monitored = sum(t.monitoring_count for t in teacher_items)
        total_targeted_support_learners = sum(t.targeted_support_count for t in teacher_items)

        total_assigned_learners = sum(t.assigned_learners_count for t in teacher_items)
        avg_learners = (
            round(total_assigned_learners / active_teachers_count, 1)
            if active_teachers_count > 0
            else 0.0
        )

        if high_workload_count > 0 and (low_workload_count > 0 or unassigned_teachers_count > 0):
            capacity_status = "Workload Imbalance Detected"
        elif high_workload_count > 0:
            capacity_status = "High System Load / Constrained Capacity"
        else:
            capacity_status = "Balanced Operating Capacity"

        summary = TeacherWorkloadSummary(
            total_teachers=total_teachers,
            active_teachers_count=active_teachers_count,
            unassigned_teachers_count=unassigned_teachers_count,
            high_workload_count=high_workload_count,
            moderate_workload_count=moderate_workload_count,
            low_workload_count=low_workload_count,
            total_learners_monitored=total_learners_monitored,
            total_targeted_support_learners=total_targeted_support_learners,
            average_learners_per_teacher=avg_learners,
            capacity_status=capacity_status,
        )

        # Generate balancing recommendations
        balancing_recs = WorkloadService._generate_balancing_recommendations(teacher_items)

        return TeacherWorkloadReportOut(
            summary=summary,
            teachers=teacher_items,
            balancing_recommendations=balancing_recs,
            scoring_methodology=SCORING_METHODOLOGY_DISCLAIMER,
            generated_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _generate_balancing_recommendations(
        teachers: List[TeacherWorkloadItem],
    ) -> List[WorkloadBalancingRecommendation]:
        """
        Produces administrative balancing recommendations based on workload comparisons.
        Considers subject specialization, class continuity, and database knowledge limitations.
        """
        recs: List[WorkloadBalancingRecommendation] = []

        high_teachers = [t for t in teachers if t.workload_status == "HIGH"]
        available_teachers = [t for t in teachers if t.workload_status in ["LOW", "UNASSIGNED"]]
        unassigned_teachers = [t for t in teachers if t.workload_status == "UNASSIGNED"]

        # 1. Subject-aware redistribution suggestions when high load and available capacity coexist
        if high_teachers and available_teachers:
            for h in high_teachers:
                # Look for a candidate with matching subject specialization in existing assignments
                matching_candidate = None
                shared_subjects: List[str] = []
                for cand in available_teachers:
                    if cand.teacher_user_id == h.teacher_user_id:
                        continue
                    shared = set(h.assigned_subjects).intersection(set(cand.assigned_subjects))
                    if shared:
                        matching_candidate = cand
                        shared_subjects = sorted(list(shared))
                        break

                if matching_candidate:
                    # Verified subject match in database
                    recs.append(
                        WorkloadBalancingRecommendation(
                            recommendation_type="REDISTRIBUTE",
                            priority="High",
                            message=(
                                f"High workload detected for {h.teacher_name} ({h.assigned_learners_count} learners, "
                                f"{h.targeted_support_count} high-support learners, score {h.workload_score:.1f}). "
                                f"{matching_candidate.teacher_name} also teaches {', '.join(shared_subjects)} with available capacity "
                                f"({matching_candidate.workload_label.lower()}, score {matching_candidate.workload_score:.1f}). "
                                f"Administrator may review redistributing a {', '.join(shared_subjects)} stream or section."
                            ),
                            source_teacher_id=h.teacher_user_id,
                            target_teacher_id=matching_candidate.teacher_user_id,
                        )
                    )
                else:
                    # No teacher with confirmed subject match in DB
                    cand = available_teachers[0]
                    recs.append(
                        WorkloadBalancingRecommendation(
                            recommendation_type="REDISTRIBUTE",
                            priority="High",
                            message=(
                                f"High workload detected for {h.teacher_name} ({h.assigned_learners_count} learners, "
                                f"{h.targeted_support_count} high-support learners in {', '.join(h.assigned_classes) or 'classes'}). "
                                f"Teacher {cand.teacher_name} has available capacity ({cand.workload_label.lower()}), but subject "
                                f"qualifications are not recorded in the database. Administrator should review subject suitability before any reassignment."
                            ),
                            source_teacher_id=h.teacher_user_id,
                            target_teacher_id=cand.teacher_user_id,
                        )
                    )

        # 2. High concentration of targeted support learners
        for t in teachers:
            if t.targeted_support_count >= 5:
                classes_str = ", ".join(t.assigned_classes) if t.assigned_classes else "assigned classes"
                recs.append(
                    WorkloadBalancingRecommendation(
                        recommendation_type="HIGH_SUPPORT_FOCUS",
                        priority="Medium",
                        message=(
                            f"{t.teacher_name} is managing {t.targeted_support_count} learners requiring "
                            f"targeted early intervention in {classes_str}. Review class support allocations or consider "
                            f"co-assigning remedial support staff (subject to administrator qualification review)."
                        ),
                        source_teacher_id=t.teacher_user_id,
                        target_teacher_id=None,
                    )
                )

        # 3. Unassigned teachers with available capacity
        for u in unassigned_teachers:
            recs.append(
                WorkloadBalancingRecommendation(
                    recommendation_type="CAPACITY_AVAILABLE",
                    priority="Low",
                    message=(
                        f"{u.teacher_name} currently has no active teaching assignments in the database. "
                        f"Operational capacity is available for new stream allocations or co-teaching, pending administrator review."
                    ),
                    source_teacher_id=None,
                    target_teacher_id=u.teacher_user_id,
                )
            )

        # 4. Fallback: System is balanced
        if not recs:
            recs.append(
                WorkloadBalancingRecommendation(
                    recommendation_type="BALANCED",
                    priority="Low",
                    message="Teacher workload distribution is currently balanced across all active staff members with no immediate redistribution required.",
                    source_teacher_id=None,
                    target_teacher_id=None,
                )
            )

        return recs

    @staticmethod
    def _get_teacher_notifications(db: Session, teacher_user_id: int) -> Tuple[int, int]:
        """
        Returns (unread_notifications_count, high_priority_notifications_count) for a teacher.
        """
        unread = (
            db.query(Notification)
            .filter(
                Notification.recipient_user_id == teacher_user_id,
                Notification.is_read == False,
            )
            .all()
        )
        unread_count = len(unread)
        high_unread_count = sum(1 for n in unread if n.priority == "High")
        return unread_count, high_unread_count
