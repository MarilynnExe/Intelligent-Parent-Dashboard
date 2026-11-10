"""Explicit fictional competency fixtures; repeat runs preserve teacher corrections."""
from datetime import timedelta
from sqlalchemy import select
from app.core.academic_calendar import term_date_range
from app.models.competency import Competency, CompetencyObservation
from app.models.student import Student
from app.models.user import User
from app.services import assignment_service
from app.services.lifecycle_service import record_change
from app.services.competency_service import notify

def seed_competencies(db, term, year):
    teacher = db.scalar(select(User).filter_by(email_or_username='demo.teacher'))
    learners = list(db.scalars(select(Student).where(Student.admission_number.in_(['DEMO-001','DEMO-004']))))
    if not teacher or teacher.full_name != 'Fictional Demo Teacher' or teacher.role != 'TEACHER' or len(learners) != 2 or any(s.last_name != 'Demo' or s.stream != 'Demo East' or s.grade_level != 'Grade 7' for s in learners):
        raise RuntimeError('Original fictional demo fixtures required; no competency records written.')
    start, end = term_date_range(term, year)
    today = assignment_service.school_today()
    if start > today:
        raise RuntimeError('Choose a current or past period for dated competency examples.')
    anchor = min(today, end)
    result = []
    for name, strand in [('Demo: Compare fractions','Fractions'),('Demo: Explain number patterns','Number patterns'),('Demo: Solve practical problems','Problem solving')]:
        skill = db.scalar(select(Competency).filter_by(name=name,grade_level='Grade 7',stream='Demo East',subject_name='Mathematics',created_by_teacher_id=teacher.user_id))
        if skill is None:
            skill = Competency(name=name,strand=strand,description='Fictional teacher-defined skill for demonstrating evidence tracking; no official curriculum mapping is claimed.',grade_level='Grade 7',stream='Demo East',subject_name='Mathematics',created_by_teacher_id=teacher.user_id)
            db.add(skill);db.flush();record_change(db,teacher,skill,'create')
            if 'practical' not in name:
                for learner in learners:
                    samples = [('APPROACHING_EXPECTATIONS',max(start,anchor-timedelta(days=3)),'Fictional evidence: needed visual prompts to explain the activity.')]
                    if 'fractions' in name:
                        samples.append(('MEETING_EXPECTATIONS',anchor,'Fictional evidence: explained the activity independently using a diagram.'))
                    for level, observed, evidence in samples:
                        row=CompetencyObservation(competency_id=skill.competency_id,student_id=learner.student_id,term=term,academic_year=year,observed_on=observed,level=level,evidence=evidence,recorded_by_teacher_id=teacher.user_id)
                        db.add(row);db.flush();record_change(db,teacher,row,'create')
        result.append(skill.competency_id)
    db.commit()
    for learner in learners:notify(db,learner,term,year)
    return result
