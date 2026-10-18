from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.academic import (
    Assessment,
    CohortPercentile,
)
from app.models.student import Student


class PercentileService:

    @staticmethod
    def calculate_subject_percentiles(
        db: Session,
        grade_level: str,
        stream: str,
        subject_name: str,
        term: str,
        academic_year: str,
    ):
        student_scores = (
            db.query(
                Assessment.student_id,
                func.avg(Assessment.percentage).label("average_score"),
            )
            .join(Student, Assessment.student_id == Student.student_id)
            .filter(
                Student.grade_level == grade_level,
                Student.stream == stream,
                Assessment.subject_name == subject_name,
                Assessment.term == term,
                Assessment.academic_year == academic_year,
            )
            .group_by(Assessment.student_id)
            .all()
        )

        if not student_scores:
            return []

        scores = [float(item.average_score) for item in student_scores]
        n = len(scores)
        results = []

        for item in student_scores:
            score = float(item.average_score)
            lower = sum(1 for x in scores if x < score)
            equal = sum(1 for x in scores if x == score)
            percentile = round(((lower + 0.5 * equal) / n) * 100, 1)

            existing = (
                db.query(CohortPercentile)
                .filter(
                    CohortPercentile.student_id == item.student_id,
                    CohortPercentile.subject_name == subject_name,
                    CohortPercentile.term == term,
                    CohortPercentile.academic_year == academic_year,
                )
                .first()
            )

            if existing:
                existing.percentile_rank = percentile
                existing.calculated_at = datetime.utcnow()
                results.append(existing)
            else:
                record = CohortPercentile(
                    student_id=item.student_id,
                    subject_name=subject_name,
                    grade_level=grade_level,
                    stream=stream,
                    term=term,
                    academic_year=academic_year,
                    percentile_rank=percentile,
                )
                db.add(record)
                results.append(record)

        db.commit()
        return results

    @staticmethod
    def calculate_overall_cohort_percentiles(
        db: Session,
        grade_level: str,
        stream: str | None,
        term: str,
        academic_year: str,
    ):
        """
        Calculate overall cohort percentile rank across all subjects for students
        in a grade/stream cohort based strictly on their assessment average in the
        specified term (e.g. Term 1).

        Stored in CohortPercentile with subject_name=None.
        """
        query = (
            db.query(
                Assessment.student_id,
                func.avg(Assessment.percentage).label("average_score"),
            )
            .join(Student, Assessment.student_id == Student.student_id)
            .filter(
                Student.grade_level == grade_level,
                Assessment.term == term,
                Assessment.academic_year == academic_year,
            )
        )
        if stream:
            query = query.filter(Student.stream == stream)

        student_scores = query.group_by(Assessment.student_id).all()

        if not student_scores:
            return []

        scores = [float(item.average_score) for item in student_scores]
        n = len(scores)
        results = []

        for item in student_scores:
            score = float(item.average_score)
            lower = sum(1 for x in scores if x < score)
            equal = sum(1 for x in scores if x == score)
            percentile = round(((lower + 0.5 * equal) / n) * 100, 1)

            existing = (
                db.query(CohortPercentile)
                .filter(
                    CohortPercentile.student_id == item.student_id,
                    CohortPercentile.subject_name.is_(None),
                    CohortPercentile.term == term,
                    CohortPercentile.academic_year == academic_year,
                )
                .first()
            )

            if existing:
                existing.percentile_rank = percentile
                existing.calculated_at = datetime.utcnow()
                results.append(existing)
            else:
                record = CohortPercentile(
                    student_id=item.student_id,
                    subject_name=None,
                    grade_level=grade_level,
                    stream=stream,
                    term=term,
                    academic_year=academic_year,
                    percentile_rank=percentile,
                )
                db.add(record)
                results.append(record)

        db.commit()
        return results

    @staticmethod
    def get_or_calculate_student_percentile(
        db: Session,
        student: Student,
        term: str,
        academic_year: str,
    ) -> float:
        """
        Retrieve overall cohort percentile for student in the given term/year.
        If not yet computed, calculates it on-the-fly from available cohort assessments.
        """
        existing = (
            db.query(CohortPercentile)
            .filter(
                CohortPercentile.student_id == student.student_id,
                CohortPercentile.subject_name.is_(None),
                CohortPercentile.term == term,
                CohortPercentile.academic_year == academic_year,
            )
            .first()
        )
        if existing:
            return float(existing.percentile_rank)

        # Calculate for cohort
        PercentileService.calculate_overall_cohort_percentiles(
            db=db,
            grade_level=student.grade_level,
            stream=student.stream,
            term=term,
            academic_year=academic_year,
        )

        refreshed = (
            db.query(CohortPercentile)
            .filter(
                CohortPercentile.student_id == student.student_id,
                CohortPercentile.subject_name.is_(None),
                CohortPercentile.term == term,
                CohortPercentile.academic_year == academic_year,
            )
            .first()
        )
        if refreshed:
            return float(refreshed.percentile_rank)

        # If student has no assessments in cohort, return median 50.0
        return 50.0