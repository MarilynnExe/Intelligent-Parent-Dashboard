"""
Expert System for Student Intervention Recommendations.

This service implements transparent, rule-based reasoning to generate actionable
parent and teacher recommendations. It integrates:
    - CatBoost support probability & status
    - Subject-level academic performance
    - Period-to-date attendance records
    - Behavioural observations

Architecture Rule:
    CatBoost provides the empirical risk prediction.
    The Expert System provides transparent, explainable pedagogical rules.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.academic import Assessment
from app.models.analytics import Recommendation
from app.models.behaviour import Attendance, BehaviourRecord
from app.models.student import Student

logger = logging.getLogger(__name__)


class ExpertSystemService:
    """
    Inference engine that evaluates transparent pedagogical rules
    and generates structured student recommendations.
    """

    @staticmethod
    def evaluate_and_generate_recommendations(
        db: Session,
        student: Student,
        term: str,
        academic_year: str,
        overall_average: float,
        cohort_percentile: float,
        support_probability: float,
        support_status: str,
        absences_count: int | float,
    ) -> List[Recommendation]:
        """
        Evaluate student context across all expert rules and persist recommendations.
        """
        generated: List[Dict[str, Any]] = []

        # -------------------------------------------------------------
        # 1. Academic Risk / Support Status Rules (CatBoost Driven)
        # -------------------------------------------------------------
        if support_status == "Targeted Support Recommended":
            generated.append({
                "rule_code": "ACAD_TARGETED_SUPPORT",
                "priority": "High",
                "target_audience": "Both",
                "text": (
                    f"Learner is flagged for targeted academic support (calibrated risk: "
                    f"{support_probability:.1%}). A collaborative parent-teacher conference "
                    f"is strongly advised to structure remedial sessions and learning goals."
                ),
            })
        elif support_status == "Monitoring Suggested":
            generated.append({
                "rule_code": "ACAD_MONITORING_SUGGESTED",
                "priority": "Medium",
                "target_audience": "Both",
                "text": (
                    f"Learner academic indicators suggest close monitoring (calibrated risk: "
                    f"{support_probability:.1%}). Regular check-ins on classwork completion "
                    f"and conceptual comprehension are recommended."
                ),
            })
        elif support_status == "On Track" and overall_average >= 75.0 and cohort_percentile >= 70.0:
            generated.append({
                "rule_code": "ACAD_COMMENDABLE_PROGRESS",
                "priority": "Low",
                "target_audience": "Parent",
                "text": (
                    f"Learner is performing commendably on track with an overall average of "
                    f"{overall_average:.1f}% (cohort percentile: {cohort_percentile:.1f}%). "
                    f"Continue positive reinforcement and encourage curiosity."
                ),
            })

        # -------------------------------------------------------------
        # 2. Subject-Specific Remediation Rules
        # -------------------------------------------------------------
        subject_averages = (
            db.query(
                Assessment.subject_name,
                func.avg(Assessment.percentage).label("avg_pct"),
            )
            .filter(
                Assessment.student_id == student.student_id,
                Assessment.term == term,
                Assessment.academic_year == academic_year,
            )
            .group_by(Assessment.subject_name)
            .all()
        )

        failing_subjects = [
            str(subj.subject_name)
            for subj in subject_averages
            if float(subj.avg_pct) < 50.0
        ]

        if failing_subjects:
            subjects_str = ", ".join(failing_subjects)
            generated.append({
                "rule_code": "ACAD_SUBJECT_DEFICIENCY",
                "priority": "High",
                "target_audience": "Both",
                "text": (
                    f"Learner is experiencing academic difficulties in: {subjects_str}. "
                    f"Targeted revision in these specific learning areas and teacher consultation "
                    f"are strongly recommended."
                ),
            })

        # -------------------------------------------------------------
        # 3. Attendance Intervention Rules
        # -------------------------------------------------------------
        if absences_count >= 3:
            generated.append({
                "rule_code": "ATTEND_EXCESSIVE_ABSENCE",
                "priority": "High",
                "target_audience": "Parent",
                "text": (
                    f"Learner has accumulated {int(absences_count)} school absences to date this term. "
                    f"Consistent daily attendance is crucial to prevent instructional gaps."
                ),
            })

        # -------------------------------------------------------------
        # 4. Behaviour & Engagement Rules
        # -------------------------------------------------------------
        low_behaviour_records = (
            db.query(BehaviourRecord)
            .filter(
                BehaviourRecord.student_id == student.student_id,
                BehaviourRecord.rating <= 2,
            )
            .all()
        )

        if low_behaviour_records:
            low_categories = sorted(list({r.category for r in low_behaviour_records}))
            categories_str = ", ".join(low_categories)
            generated.append({
                "rule_code": "BEHAV_ATTENTION_REQUIRED",
                "priority": "Medium",
                "target_audience": "Parent",
                "text": (
                    f"Recent classroom observations indicate areas needing attention in: {categories_str}. "
                    f"Reinforcing school routines and positive study habits at home will assist the learner."
                ),
            })

        # -------------------------------------------------------------
        # 5. Persist / Refresh Recommendations in Database
        # -------------------------------------------------------------
        # Archive existing active recommendations for this student, term, and year
        db.query(Recommendation).filter(
            Recommendation.student_id == student.student_id,
            Recommendation.term == term,
            Recommendation.academic_year == academic_year,
            Recommendation.status == "Active",
        ).update({"status": "Superseded"}, synchronize_session=False)

        persisted: List[Recommendation] = []
        for rec_data in generated:
            rec = Recommendation(
                student_id=student.student_id,
                term=term,
                academic_year=academic_year,
                rule_code=rec_data["rule_code"],
                recommendation_text=rec_data["text"],
                target_audience=rec_data["target_audience"],
                priority=rec_data["priority"],
                generated_at=datetime.utcnow(),
                status="Active",
            )
            db.add(rec)
            persisted.append(rec)

        db.commit()
        logger.info(
            "Generated %d expert recommendations for student %d (%s, %s)",
            len(persisted),
            student.student_id,
            term,
            academic_year,
        )

        return persisted
