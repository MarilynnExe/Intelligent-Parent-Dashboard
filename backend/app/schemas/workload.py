"""
Pydantic Schemas for Teacher Workload Balancer.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class TeacherWorkloadItem(BaseModel):
    teacher_user_id: int
    teacher_name: str
    email_or_username: str
    assigned_classes: List[str]
    assigned_subjects: List[str]
    total_classes_count: int
    subject_assignments_count: int
    assigned_learners_count: int
    targeted_support_count: int
    monitoring_count: int
    on_track_count: int
    unassessed_learners_count: int
    unread_notifications_count: int
    high_priority_notifications_count: int
    workload_score: float
    workload_status: str  # "HIGH", "MODERATE", "LOW", "UNASSIGNED"
    workload_label: str  # "High Workload", "Moderate Workload", "Available Capacity", "No Active Assignments"
    explanation: str

    model_config = ConfigDict(from_attributes=True)


class WorkloadBalancingRecommendation(BaseModel):
    recommendation_type: str  # "REDISTRIBUTE", "HIGH_SUPPORT_FOCUS", "CAPACITY_AVAILABLE", "BALANCED"
    priority: str  # "High", "Medium", "Low"
    message: str
    source_teacher_id: Optional[int] = None
    target_teacher_id: Optional[int] = None


class TeacherWorkloadSummary(BaseModel):
    total_teachers: int
    active_teachers_count: int
    unassigned_teachers_count: int
    high_workload_count: int
    moderate_workload_count: int
    low_workload_count: int
    total_learners_monitored: int
    total_targeted_support_learners: int
    average_learners_per_teacher: float
    capacity_status: str


class TeacherWorkloadReportOut(BaseModel):
    summary: TeacherWorkloadSummary
    teachers: List[TeacherWorkloadItem]
    balancing_recommendations: List[WorkloadBalancingRecommendation]
    scoring_methodology: str
    generated_at: datetime
