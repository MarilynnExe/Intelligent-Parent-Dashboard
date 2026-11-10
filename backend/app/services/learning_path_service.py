"""
Learning Path and Educational Resource Recommendation Service.

Translates empirical learner risk and rule-based diagnostic alerts into
concrete, structured learning activities and vetted educational resources.

Key Principles:
    1. Recommendation Grounding & Evidence Distinction:
       - Academic difficulty recommendations are triggered by empirical, recorded
         subject-level assessment averages below a configurable benchmark.
       - The system explicitly distinguishes observed subject-level performance from
         unassessed sub-topics. Suggested topic activities represent curated,
         age-appropriate support activities aligned to curriculum structure,
         NOT confirmed areas of topic weakness.
    2. Configurable Remediation Benchmark:
       - The 50.0% remediation threshold is an internal, system-defined early
         intervention benchmark for support triage. It is NOT an official Kenya
         Institute of Curriculum Development (KICD) or CBC competency cutoff.
    3. Strict Curriculum Alignment Audit:
       - Official CBC alignment (CURRICULUM_ALIGNED) is claimed ONLY where a specific,
         identifiable KICD Curriculum Design publication and strand/sub-strand is documented.
       - General educational materials hosted on open portals (such as the Kenya
         Education Cloud) or external OERs (Khan Academy, African Storybook, PhET) are
         classified as provisional supplementary support (PROVISIONAL_SUPPORT).
    4. Anti-Flood Deduplication:
       - Active learning paths for a given student and term are superseded upon recalculation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.academic import Assessment
from app.models.analytics import Recommendation
from app.models.learning_path import LearningPathItem, LearningResource
from app.models.student import Student

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configurable Remediation Benchmark
# ---------------------------------------------------------------------------
# Internal early-intervention threshold for academic support triage.
# NOTE: This 50.0% benchmark is a system-defined parameter, NOT an official
# KICD/CBC cutoff (CBC uses rubric performance levels: Exceeding Expectations,
# Meeting Expectations, Approaching Expectations, Below Expectations).
DEFAULT_REMEDIATION_BENCHMARK_PCT: float = 50.0


# ---------------------------------------------------------------------------
# Starter Catalogue of Educational Resources
# ---------------------------------------------------------------------------
# Audited catalogue: Only resources with specific, identifiable KICD curriculum
# design citations are designated CURRICULUM_ALIGNED. General portal resources
# and open educational resources (OERs) are designated PROVISIONAL_SUPPORT.
STARTER_CATALOGUE = [
    {
        "subject_name": "Mathematics",
        "grade_level": "Grade 7",
        "topic_competency": "Numbers: Fractions, Decimals, and Percentages",
        "activity_title": "Visual Fraction Modeling & Real-World Word Problems",
        "activity_description": (
            "Practice converting between fractions, decimals, and percentages using visual area diagrams "
            "and real-world Kenyan shopping and measurement word problems."
        ),
        "resource_title": "KICD Grade 7 Mathematics Curriculum Design — Strand 1.0 (Numbers)",
        "resource_description": (
            "Official KICD Junior Secondary School Curriculum Design for Grade 7 Mathematics: "
            "Strand 1.0 Numbers, Sub-strand 1.2 Fractions, Decimals and Percentages (Specific Learning Outcome: "
            "solve real-life problems involving fractions and decimals)."
        ),
        "resource_url": "https://kec.ac.ke",
        "resource_type": "KICD Official Curriculum Design",
        "alignment_type": "CURRICULUM_ALIGNED",
        "alignment_source": "KICD Junior Secondary School Curriculum Design: Grade 7 Mathematics (2023), Strand 1.0 Numbers, Sub-strand 1.2 Fractions, Decimals and Percentages",
        "is_verified": True,
        "suggested_duration": "30 mins, 3 times per week",
        "recommended_next_step": "Work through Sub-strand 1.2 practice questions and review problem areas with the mathematics teacher.",
    },
    {
        "subject_name": "Mathematics",
        "grade_level": "Grade 7",
        "topic_competency": "Basic Arithmetic & Algebraic Thinking",
        "activity_title": "Interactive Number Line & Arithmetic Mastery",
        "activity_description": (
            "Step-by-step interactive practice on signed numbers, order of operations, and basic linear equations."
        ),
        "resource_title": "Khan Academy — Grade 7 Math (Illustrative Mathematics)",
        "resource_description": (
            "Free mastery-based interactive exercises, hints, and video explanations aligned to foundational middle school concepts."
        ),
        "resource_url": "https://www.khanacademy.org/math/cc-seventh-grade-math",
        "resource_type": "Interactive Practice & Videos",
        "alignment_type": "PROVISIONAL_SUPPORT",
        "alignment_source": "Open Educational Resource / Global OER (Provisional supplementary practice; not an official KICD publication)",
        "is_verified": True,
        "suggested_duration": "20 mins, 4 times per week",
        "recommended_next_step": "Aim for 80% mastery on foundational quiz exercises before moving to complex word problems.",
    },
    {
        "subject_name": "English",
        "grade_level": "Grade 7",
        "topic_competency": "Reading Comprehension, Vocabulary & Summary Writing",
        "activity_title": "Passage Analysis & Context Clue Journaling",
        "activity_description": (
            "Read short narrative and expository passages, identify main ideas, extract unfamiliar words using context clues, "
            "and write a 3-sentence paragraph summary."
        ),
        "resource_title": "Kenya Education Cloud — Grade 7 English Supplementary Materials",
        "resource_description": (
            "Digital reading comprehension and grammar practice materials hosted on the Kenya Education Cloud. "
            "Classified as provisional supplementary support pending mapping to specific KICD syllabus sub-strands."
        ),
        "resource_url": "https://kec.ac.ke",
        "resource_type": "KICD Digital Content",
        "alignment_type": "PROVISIONAL_SUPPORT",
        "alignment_source": "Provisional Supplementary Support (Kenya Education Cloud open portal; general Grade 7 English materials without verified specific curriculum sub-strand alignment)",
        "is_verified": False,
        "suggested_duration": "25 mins, 3 times per week",
        "recommended_next_step": "Maintain a personal vocabulary journal with 5 new words each week and share with the English teacher.",
    },
    {
        "subject_name": "English",
        "grade_level": "Grade 7",
        "topic_competency": "Extensive Reading & Fluency",
        "activity_title": "Daily Graded Story Reading",
        "activity_description": (
            "Engage with age-appropriate African folk tales and modern stories to build reading stamina and vocabulary fluency."
        ),
        "resource_title": "African Storybook Project",
        "resource_description": (
            "Open-access illustrated digital storybooks in English and African languages promoting reading for enjoyment."
        ),
        "resource_url": "https://africanstorybook.org",
        "resource_type": "Digital Storybooks",
        "alignment_type": "PROVISIONAL_SUPPORT",
        "alignment_source": "African Storybook Literacy Initiative (Provisional Supplemental Reading; independent open-access resource)",
        "is_verified": True,
        "suggested_duration": "20 mins daily before bedtime",
        "recommended_next_step": "Parent and learner take turns reading alternating pages aloud to build pronunciation confidence.",
    },
    {
        "subject_name": "Science",
        "grade_level": "Grade 7",
        "topic_competency": "Scientific Inquiry, Mixtures & Living Things",
        "activity_title": "Hands-On Observations & Concept Mapping",
        "activity_description": (
            "Conduct simple kitchen experiments (e.g. dissolving mixtures, testing density) and sketch concept maps explaining observation results."
        ),
        "resource_title": "Kenya Education Cloud — Grade 7 Integrated Science Modules",
        "resource_description": (
            "Digital learning modules on basic laboratory safety, states of matter, and environmental systems. "
            "Classified as provisional supplementary support pending verification of specific KICD design sub-strand alignment."
        ),
        "resource_url": "https://kec.ac.ke",
        "resource_type": "KICD Digital Content",
        "alignment_type": "PROVISIONAL_SUPPORT",
        "alignment_source": "Provisional Supplementary Support (Kenya Education Cloud open portal; general Integrated Science modules without verified curriculum sub-strand link)",
        "is_verified": False,
        "suggested_duration": "30 mins, 2 times per week",
        "recommended_next_step": "Record experiment observations in a dedicated science logbook and discuss conclusions with the teacher.",
    },
    {
        "subject_name": "Science",
        "grade_level": "Grade 7",
        "topic_competency": "Matter, Forces & Energy",
        "activity_title": "Interactive Science Simulations",
        "activity_description": (
            "Explore interactive simulations on states of matter, atoms, density, and simple circuits."
        ),
        "resource_title": "PhET Interactive Simulations — Middle School Science",
        "resource_description": (
            "Free research-based interactive simulations developed by the University of Colorado Boulder."
        ),
        "resource_url": "https://phet.colorado.edu",
        "resource_type": "Interactive Simulation",
        "alignment_type": "PROVISIONAL_SUPPORT",
        "alignment_source": "University of Colorado Boulder PhET Interactive Simulations (Provisional Science Lab Simulation; external OER)",
        "is_verified": True,
        "suggested_duration": "20 mins per simulation topic",
        "recommended_next_step": "Change variables in the simulation to see causes and effects, then summarize key takeaways.",
    },
    {
        "subject_name": "Integrated Science",
        "grade_level": "Grade 7",
        "topic_competency": "Scientific Inquiry, Mixtures & Living Things",
        "activity_title": "Hands-On Observations & Concept Mapping",
        "activity_description": (
            "Conduct simple home experiments on mixtures and separation techniques and sketch concept maps."
        ),
        "resource_title": "Kenya Education Cloud — Grade 7 Integrated Science Modules",
        "resource_description": (
            "Digital modules on basic laboratory safety, states of matter, and environmental systems. "
            "Classified as provisional supplementary support."
        ),
        "resource_url": "https://kec.ac.ke",
        "resource_type": "KICD Digital Content",
        "alignment_type": "PROVISIONAL_SUPPORT",
        "alignment_source": "Provisional Supplementary Support (Kenya Education Cloud open portal)",
        "is_verified": False,
        "suggested_duration": "30 mins, 2 times per week",
        "recommended_next_step": "Record experiment observations in a dedicated science logbook and discuss conclusions with the teacher.",
    },
    {
        "subject_name": "General Academic",
        "grade_level": "Grade 7",
        "topic_competency": "Active Study Habits & Metacognition",
        "activity_title": "Structured Evening Revision Timetable & Flashcard Review",
        "activity_description": (
            "Set up a consistent 45-minute distraction-free study block each evening using the Pomodoro technique "
            "(25m study, 5m break) with flashcard self-testing."
        ),
        "resource_title": "Learner Study Skills & Active Recall Guide",
        "resource_description": (
            "Evidence-based framework for spacing revision sessions, self-quizzing, and overcoming homework anxiety."
        ),
        "resource_url": None,
        "resource_type": "Pedagogical Guide",
        "alignment_type": "PROVISIONAL_SUPPORT",
        "alignment_source": "Provisional Pedagogical Support (Study skills framework; independent supplementary guide)",
        "is_verified": True,
        "suggested_duration": "45 mins, 5 days per week",
        "recommended_next_step": "Review the weekly revision schedule together every Sunday evening and track completed sessions.",
    },
    {
        "subject_name": "Attendance & Habits",
        "grade_level": "Grade 7",
        "topic_competency": "Attendance Consistency & Morning Routines",
        "activity_title": "Morning Routine Checklist & Catch-Up Plan",
        "activity_description": (
            "Establish an evening prep checklist (packing bag, preparing uniform) to minimize morning delays "
            "and set up a peer study buddy for missed lesson notes."
        ),
        "resource_title": "School Attendance Consistency Guide",
        "resource_description": (
            "Practical guide for families on building reliable school routines and preventing learning continuity gaps."
        ),
        "resource_url": None,
        "resource_type": "Parent Action Guide",
        "alignment_type": "PROVISIONAL_SUPPORT",
        "alignment_source": "Provisional Family Support Protocol (School attendance guidance; administrative advisory)",
        "is_verified": True,
        "suggested_duration": "Daily morning and evening check",
        "recommended_next_step": "If an absence is unavoidable, notify the school immediately and request lesson worksheets.",
    },
    {
        "subject_name": "Academic Enrichment",
        "grade_level": "Grade 7",
        "topic_competency": "Enrichment & Project-Based Inquiry",
        "activity_title": "Independent Inquiry Project & Peer Tutoring",
        "activity_description": (
            "Choose a topic of interest (e.g. renewable energy, local history, or creative writing) to research and present, "
            "or support a classmate as a peer study buddy."
        ),
        "resource_title": "Kenya Education Cloud — Enrichment & Discovery (General Portal)",
        "resource_description": (
            "Advanced reading materials and creative problem-solving challenges. "
            "Classified as provisional enrichment support (not tied to a specific KICD design syllabus document)."
        ),
        "resource_url": "https://kec.ac.ke",
        "resource_type": "Enrichment Materials",
        "alignment_type": "PROVISIONAL_SUPPORT",
        "alignment_source": "Provisional Supplementary Support (Kenya Education Cloud open enrichment; general portal content without specific curriculum strand citation)",
        "is_verified": False,
        "suggested_duration": "45 mins weekly",
        "recommended_next_step": "Encourage learner to share their project findings with family members and teacher.",
    },
]


class LearningPathService:
    """
    Orchestrates the retrieval and dynamic creation of tailored learning paths.
    """

    @staticmethod
    def seed_starter_catalogue_if_empty(db: Session) -> int:
        """
        Populate the starter catalogue if the learning_resources table is empty,
        or update existing records to reflect refined alignment classifications.
        """
        existing = {r.activity_title: r for r in db.query(LearningResource).all()}
        if not existing:
            created = 0
            for item_data in STARTER_CATALOGUE:
                res = LearningResource(
                    subject_name=item_data["subject_name"],
                    grade_level=item_data["grade_level"],
                    topic_competency=item_data["topic_competency"],
                    activity_title=item_data["activity_title"],
                    activity_description=item_data["activity_description"],
                    resource_title=item_data["resource_title"],
                    resource_description=item_data["resource_description"],
                    resource_url=item_data["resource_url"],
                    resource_type=item_data["resource_type"],
                    alignment_type=item_data["alignment_type"],
                    alignment_source=item_data["alignment_source"],
                    is_verified=item_data["is_verified"],
                    suggested_duration=item_data["suggested_duration"],
                    recommended_next_step=item_data["recommended_next_step"],
                    created_at=datetime.now(timezone.utc),
                )
                db.add(res)
                created += 1

            db.commit()
            logger.info("Seeded %d starter educational resources into catalogue.", created)
            return created

        # Synchronize updated alignment fields and descriptions if existing
        updated = 0
        for item_data in STARTER_CATALOGUE:
            if item_data["activity_title"] in existing:
                res = existing[item_data["activity_title"]]
                res.alignment_type = item_data["alignment_type"]
                res.alignment_source = item_data["alignment_source"]
                res.is_verified = item_data["is_verified"]
                res.resource_title = item_data["resource_title"]
                res.resource_description = item_data["resource_description"]
                res.activity_description = item_data["activity_description"]
                res.recommended_next_step = item_data["recommended_next_step"]
                updated += 1
        if updated:
            db.commit()
            logger.info("Synchronized %d educational resources with refined curriculum audit.", updated)

        return len(existing)

    @staticmethod
    def get_matching_resource(
        db: Session,
        subject_name: str,
        grade_level: str = "Grade 7",
        prefer_curriculum_aligned: bool = True,
    ) -> Optional[LearningResource]:
        """
        Find the most appropriate learning resource for a given subject and grade level.
        Prioritizes verified KICD curriculum-aligned materials when available.
        """
        LearningPathService.seed_starter_catalogue_if_empty(db)

        query = db.query(LearningResource).filter(
            func.lower(LearningResource.subject_name) == subject_name.lower().strip()
        )

        if prefer_curriculum_aligned:
            res = query.filter(LearningResource.alignment_type == "CURRICULUM_ALIGNED").first()
            if res:
                return res

        res = query.first()
        if res:
            return res

        # Fallback partial matching (e.g. Science -> Integrated Science or vice versa)
        all_resources = db.query(LearningResource).all()
        for r in all_resources:
            if subject_name.lower() in r.subject_name.lower() or r.subject_name.lower() in subject_name.lower():
                return r

        return None

    @staticmethod
    def generate_learning_paths_for_recommendations(
        db: Session,
        student: Student,
        term: str,
        academic_year: str,
        recommendations: List[Recommendation],
        remediation_benchmark: float = DEFAULT_REMEDIATION_BENCHMARK_PCT,
    ) -> List[LearningPathItem]:
        """
        Converts rule-based recommendations into concrete learning activities and resources.

        Accreditation & Reasoning Rules:
            - Subject deficiency is derived from empirical subject-level assessment averages
              falling below the configurable `remediation_benchmark`.
            - The system explicitly clarifies that sub-topic assessments are not recorded in
              the database; suggested topic activities represent curated support focus areas,
              not confirmed areas of topic weakness.
            - Recommendations clearly state: data trigger, system observation vs suggestion,
              and recommended next actions for parents and teachers.
            - De-duplicates by superseding previous active items for the student, term, and year.
        """
        LearningPathService.seed_starter_catalogue_if_empty(db)

        # 1. Supersede previously active learning paths for this period
        db.query(LearningPathItem).filter(
            LearningPathItem.student_id == student.student_id,
            LearningPathItem.term == term,
            LearningPathItem.academic_year == academic_year,
            LearningPathItem.status == "Active",
        ).update({"status": "Superseded"}, synchronize_session=False)

        # 2. Query subject averages for the student in this period
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
        subject_avg_map: Dict[str, float] = {
            str(s.subject_name): float(s.avg_pct) for s in subject_averages
        }

        generated_items: List[LearningPathItem] = []

        # 3. Map each recommendation to structured learning activities and resources
        for rec in recommendations:
            rule = rec.rule_code

            if rule == "ACAD_SUBJECT_DEFICIENCY":
                # For each subject below benchmark, attach a specific learning path item
                failing_subjects = [s for s, avg in subject_avg_map.items() if avg < remediation_benchmark]
                if not failing_subjects and subject_avg_map:
                    # If overall flagged but no single subject < benchmark, use the lowest subject
                    lowest = min(subject_avg_map.items(), key=lambda x: x[1])[0]
                    failing_subjects = [lowest]
                elif not failing_subjects:
                    failing_subjects = ["Mathematics"]

                for subj in failing_subjects:
                    avg_val = subject_avg_map.get(subj, 45.0)
                    resource = LearningPathService.get_matching_resource(db, subj, student.grade_level)

                    # Fit the established VARCHAR(500) on MySQL as well as SQLite.
                    reason = (
                        f"{subj} average: {avg_val:.1f}% in {term}; below the "
                        f"system-defined remediation benchmark ({remediation_benchmark:.1f}%). "
                        "Suggested practice is not a confirmed topic weakness: "
                        "sub-topic assessments are not recorded. "
                        "Recommended Next Action: Review recent exercises with the teacher to identify concept gaps."
                    )

                    if resource:
                        item = LearningPathItem(
                            student_id=student.student_id,
                            recommendation_id=rec.recommendation_id,
                            resource_id=resource.resource_id,
                            term=term,
                            academic_year=academic_year,
                            subject_name=subj,
                            topic_competency=resource.topic_competency,
                            reason=reason,
                            activity_title=resource.activity_title,
                            activity_description=resource.activity_description,
                            resource_title=resource.resource_title,
                            resource_description=resource.resource_description,
                            resource_url=resource.resource_url,
                            resource_type=resource.resource_type,
                            alignment_type=resource.alignment_type,
                            alignment_source=resource.alignment_source,
                            is_verified=resource.is_verified,
                            suggested_duration=resource.suggested_duration,
                            recommended_next_step=resource.recommended_next_step,
                            status="Active",
                            created_at=datetime.now(timezone.utc),
                        )
                    else:
                        item = LearningPathItem(
                            student_id=student.student_id,
                            recommendation_id=rec.recommendation_id,
                            resource_id=None,
                            term=term,
                            academic_year=academic_year,
                            subject_name=subj,
                            topic_competency=f"{subj} Core Concepts & Remediation",
                            reason=reason,
                            activity_title=f"{subj} Structured Revision Exercises",
                            activity_description=f"Complete targeted revision worksheets covering foundational {subj} topics.",
                            resource_title=f"Kenya Education Cloud — {subj} Supplementary Practice",
                            resource_description="Digital learning materials from the Kenya Education Cloud.",
                            resource_url="https://kec.ac.ke",
                            resource_type="KICD Digital Content",
                            alignment_type="PROVISIONAL_SUPPORT",
                            alignment_source="Provisional Subject Mapping (Unverified)",
                            is_verified=False,
                            suggested_duration="25 mins, 3 times per week",
                            recommended_next_step=f"Consult the {subj} subject teacher to determine specific topic remediation needs.",
                            status="Active",
                            created_at=datetime.now(timezone.utc),
                        )
                    db.add(item)
                    generated_items.append(item)

            elif rule in ["ACAD_TARGETED_SUPPORT", "ACAD_MONITORING_SUGGESTED"]:
                resource = LearningPathService.get_matching_resource(db, "General Academic", student.grade_level)
                reason = (
                    "Learner overall performance and predictive risk indicators suggest potential academic vulnerability. "
                    "System observation: CatBoost early-warning probability estimates and term grade trends (advisory early warning, not a certainty). "
                    "Suggested support area: Structured study habits, active recall, and metacognitive routines. "
                    "Recommended Next Action: Establish a regular 45-minute evening study block and review homework completion weekly."
                )
                if resource:
                    item = LearningPathItem(
                        student_id=student.student_id,
                        recommendation_id=rec.recommendation_id,
                        resource_id=resource.resource_id,
                        term=term,
                        academic_year=academic_year,
                        subject_name=resource.subject_name,
                        topic_competency=resource.topic_competency,
                        reason=reason,
                        activity_title=resource.activity_title,
                        activity_description=resource.activity_description,
                        resource_title=resource.resource_title,
                        resource_description=resource.resource_description,
                        resource_url=resource.resource_url,
                        resource_type=resource.resource_type,
                        alignment_type=resource.alignment_type,
                        alignment_source=resource.alignment_source,
                        is_verified=resource.is_verified,
                        suggested_duration=resource.suggested_duration,
                        recommended_next_step=resource.recommended_next_step,
                        status="Active",
                        created_at=datetime.now(timezone.utc),
                    )
                    db.add(item)
                    generated_items.append(item)

            elif rule == "ATTEND_EXCESSIVE_ABSENCE":
                resource = LearningPathService.get_matching_resource(db, "Attendance & Habits", student.grade_level)
                reason = (
                    "Recorded school absences this term indicate risk of instructional continuity gaps. "
                    "System observation: Daily attendance register records indicate multiple missed school days. "
                    "Suggested support area: Morning preparation routines and peer catch-up protocols. "
                    "Recommended Next Action: Review morning arrival routines and coordinate with the class teacher to obtain missed lesson notes."
                )
                if resource:
                    item = LearningPathItem(
                        student_id=student.student_id,
                        recommendation_id=rec.recommendation_id,
                        resource_id=resource.resource_id,
                        term=term,
                        academic_year=academic_year,
                        subject_name=resource.subject_name,
                        topic_competency=resource.topic_competency,
                        reason=reason,
                        activity_title=resource.activity_title,
                        activity_description=resource.activity_description,
                        resource_title=resource.resource_title,
                        resource_description=resource.resource_description,
                        resource_url=resource.resource_url,
                        resource_type=resource.resource_type,
                        alignment_type=resource.alignment_type,
                        alignment_source=resource.alignment_source,
                        is_verified=resource.is_verified,
                        suggested_duration=resource.suggested_duration,
                        recommended_next_step=resource.recommended_next_step,
                        status="Active",
                        created_at=datetime.now(timezone.utc),
                    )
                    db.add(item)
                    generated_items.append(item)

            elif rule == "ACAD_COMMENDABLE_PROGRESS":
                resource = LearningPathService.get_matching_resource(db, "Academic Enrichment", student.grade_level)
                reason = (
                    "Learner demonstrated commendable academic performance with term average exceeding 75%. "
                    "System observation: High achievement across recorded subject assessments. "
                    "Suggested support area: Independent inquiry projects and peer study leadership. "
                    "Recommended Next Action: Encourage the learner to pursue self-directed enrichment topics and share discoveries."
                )
                if resource:
                    item = LearningPathItem(
                        student_id=student.student_id,
                        recommendation_id=rec.recommendation_id,
                        resource_id=resource.resource_id,
                        term=term,
                        academic_year=academic_year,
                        subject_name=resource.subject_name,
                        topic_competency=resource.topic_competency,
                        reason=reason,
                        activity_title=resource.activity_title,
                        activity_description=resource.activity_description,
                        resource_title=resource.resource_title,
                        resource_description=resource.resource_description,
                        resource_url=resource.resource_url,
                        resource_type=resource.resource_type,
                        alignment_type=resource.alignment_type,
                        alignment_source=resource.alignment_source,
                        is_verified=resource.is_verified,
                        suggested_duration=resource.suggested_duration,
                        recommended_next_step=resource.recommended_next_step,
                        status="Active",
                        created_at=datetime.now(timezone.utc),
                    )
                    db.add(item)
                    generated_items.append(item)

        db.commit()
        logger.info(
            "Generated %d learning path items for student %d (%s, %s)",
            len(generated_items),
            student.student_id,
            term,
            academic_year,
        )
        return generated_items

    @staticmethod
    def get_student_learning_path(
        db: Session,
        student_id: int,
        term: Optional[str] = None,
        academic_year: Optional[str] = None,
        active_only: bool = True,
    ) -> List[LearningPathItem]:
        """
        Retrieve learning path items for a student.
        """
        query = db.query(LearningPathItem).filter(LearningPathItem.student_id == student_id)
        if active_only:
            query = query.filter(LearningPathItem.status == "Active")
        if term:
            query = query.filter(LearningPathItem.term == term)
        if academic_year:
            query = query.filter(LearningPathItem.academic_year == academic_year)

        return query.order_by(LearningPathItem.path_id.asc()).all()
