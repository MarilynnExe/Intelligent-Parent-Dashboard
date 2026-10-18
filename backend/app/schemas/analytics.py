from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


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

    model_config = ConfigDict(from_attributes=True)


class StudentAnalyticsOut(BaseModel):
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

    model_config = ConfigDict(from_attributes=True)


class CalculateAnalyticsRequest(BaseModel):
    term: str = "Term 1"
    academic_year: str = "2026"
