from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class LearningPathItemOut(BaseModel):
    path_id: int
    recommendation_id: Optional[int] = None
    student_id: int
    term: str
    academic_year: str
    subject_name: str
    topic_competency: str
    reason: str
    activity_title: str
    activity_description: str
    resource_title: str
    resource_description: Optional[str] = None
    resource_url: Optional[str] = None
    resource_type: Optional[str] = None
    alignment_type: str  # "CURRICULUM_ALIGNED" vs "PROVISIONAL_SUPPORT"
    alignment_source: Optional[str] = None
    is_verified: bool
    suggested_duration: Optional[str] = None
    recommended_next_step: Optional[str] = None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LearningResourceOut(BaseModel):
    resource_id: int
    subject_name: str
    grade_level: str
    topic_competency: str
    activity_title: str
    activity_description: str
    resource_title: str
    resource_description: Optional[str] = None
    resource_url: Optional[str] = None
    resource_type: str
    alignment_type: str
    alignment_source: Optional[str] = None
    is_verified: bool
    suggested_duration: Optional[str] = None
    recommended_next_step: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RecommendationOut(BaseModel):
    recommendation_id: int
    student_id: int
    term: str
    academic_year: str
    rule_code: str
    recommendation_text: str
    target_audience: str
    priority: str
    status: str
    generated_at: datetime
    learning_path: Optional[LearningPathItemOut] = None

    model_config = ConfigDict(from_attributes=True)


class StudentAnalyticsOut(BaseModel):
    freshness: str = "stale"
    is_current: bool = False
    freshness_message: Optional[str] = None
    analytics_id: int
    student_id: int
    term: str
    academic_year: str
    overall_average: Optional[float] = None
    support_probability: Optional[float] = None
    support_status: Optional[str] = None
    calculated_at: datetime
    cohort_percentile: Optional[float] = None
    absences_count: Optional[int] = None
    recommendations: List[RecommendationOut] = Field(default_factory=list)
    learning_path: List[LearningPathItemOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class CalculateAnalyticsRequest(BaseModel):
    # None means the current term, worked out from today's date
    term: Optional[str] = None
    academic_year: Optional[str] = None
