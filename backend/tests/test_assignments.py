"""Assignment tracking without changing academic-model inputs."""
from datetime import date, datetime, timezone
import pytest
from sqlalchemy import select, func
from app.models.assignment import ClassAssignment, AssignmentCompletion
from app.models.academic import Assessment
from app.models.analytics import StudentAnalytics
from app.models.lifecycle import RecordChange
from app.models.notification import Notification
from app.models.student import Student
from app.services import assignment_service as service
from test_crud_audit import audit

REAL_SCHOOL_TODAY = service.school_today

PERIOD = dict(term='Term 3', academic_year='2026')
WORK = dict(title='Fractions practice',instructions='Complete the worksheet.',grade_level='Grade 7',stream='Demo East',subject_name='Mathematics',**PERIOD,assigned_date='2026-11-01',due_date='2026-11-08')

@pytest.fixture(autouse=True)
def today(monkeypatch):
    monkeypatch.setattr(service,'school_today',lambda:date(2026,11,10))

def create(audit, **changes):
    c,h,_,_,_=audit
    r=c.post('/api/teacher/class-assignments',headers=h['teacher'],json={**WORK,**changes})
    assert r.status_code==201,r.text
    return r.json()

def report(audit, student='Amina', **params):
    c,h,_,students,_=audit
    r=c.get(f"/api/parent/children/{students[student]}/assignments",headers=h['parent'],params={**PERIOD,**params})
    assert r.status_code==200,r.text
    return r.json()

def submit(audit, key, entries):
    c,h,_,_,_=audit
    return c.put(f'/api/teacher/class-assignments/{key}/completions',headers=h['teacher'],json={'entries':entries})

def entry(audit, student='Amina', **changes):
    return dict(student_id=audit[3][student],status='SUBMITTED',submitted_on='2026-11-09',reason='Illness delayed submission',**changes)


def test_create_register_missing_and_model_unchanged(audit):
    c,h,_,students,sessions=audit
    with sessions() as db:
        before=[(r.analytics_id,r.support_probability,r.overall_average,r.calculated_at) for r in db.scalars(select(StudentAnalytics))]
        assessments=db.scalar(select(func.count()).select_from(Assessment))
    row=create(audit)
    data=report(audit)
    assert data['counts']['MISSING']==1 and data['completion_rate']==0
    assert data['guidance'][0]['rule_code']=='ASSIGNMENT_MISSING_WORK'
    register=c.get(f"/api/teacher/class-assignments/{row['assignment_id']}/register",headers=h['teacher']).json()
    assert len(register['recipients'])==4 and all(r['editable'] for r in register['recipients'])
    assert students['Esther'] not in {r['student_id'] for r in register['recipients']}
    with sessions() as db:
        assert before==[(r.analytics_id,r.support_probability,r.overall_average,r.calculated_at) for r in db.scalars(select(StudentAnalytics))]
        assert db.scalar(select(func.count()).select_from(Assessment))==assessments


def test_missing_is_derived_at_nairobi_deadline_without_writes(audit,monkeypatch):
    row=create(audit,due_date='2026-11-10')
    assert report(audit)['counts']['PENDING']==1
    monkeypatch.setattr(service,'school_today',lambda:date(2026,11,11))
    assert report(audit)['counts']['MISSING']==1
    with audit[4]() as db:
        completion=db.scalar(select(AssignmentCompletion).filter_by(assignment_id=row['assignment_id'],student_id=audit[3]['Amina']))
        assert completion.status=='NOT_SUBMITTED'


def test_late_reason_required_and_atomic_bulk_validation(audit):
    row=create(audit);key=row['assignment_id']
    result=submit(audit,key,[{**entry(audit), 'reason':'   '}])
    assert result.status_code==400
    result=submit(audit,key,[entry(audit),{**entry(audit,'Brian'),'reason':None}])
    assert result.status_code==400
    assert report(audit)['counts']['MISSING']==1
    assert submit(audit,key,[entry(audit)]).status_code==200
    data=report(audit)
    assert data['counts']['LATE']==1 and data['completion_rate']==100 and data['guidance']==[]
    assert data['assignments'][0]['reason']=='Illness delayed submission'
    assert submit(audit,key,[entry(audit),entry(audit)]).status_code==422


def test_excused_zero_denominator_and_pending_not_in_rate(audit):
    late=create(audit);create(audit,title='Upcoming work',due_date='2026-11-17')
    result=submit(audit,late['assignment_id'],[dict(student_id=audit[3]['Amina'],status='EXCUSED',reason='Medical exemption')])
    assert result.status_code==200
    data=report(audit)
    assert data['due_count']==0 and data['completion_rate'] is None
    assert data['counts']['PENDING']==1 and data['counts']['EXCUSED']==1
    assert data['guidance']==[]


def test_new_enrollment_receives_only_open_work_once(audit):
    c,h,_,_,sessions=audit
    old=create(audit);future=create(audit,title='Current work',due_date='2026-11-17')
    payload=dict(admission_number='NEW-CLASS',first_name='New',last_name='Learner',date_of_birth='2013-01-01',grade_level='Grade 7',stream='Demo East')
    result=c.post('/api/admin/students',headers=h['admin'],json=payload)
    assert result.status_code==201,result.text
    student=result.json()['student_id']
    with sessions() as db:
        rows=db.scalars(select(AssignmentCompletion).filter_by(student_id=student)).all()
        assert [r.assignment_id for r in rows]==[future['assignment_id']]
    assert c.put(f'/api/admin/students/{student}',headers=h['admin'],json=payload).status_code==200
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(AssignmentCompletion).filter_by(student_id=student))==1


def test_transfer_and_archive_preserve_readonly_history_and_restore_sync(audit):
    c,h,_,students,sessions=audit
    past=create(audit);future=create(audit,title='Open work',due_date='2026-11-17')
    student=next(s for s in c.get('/api/admin/students',headers=h['admin']).json() if s['student_id']==students['Amina'])
    payload={k:student[k] for k in ('admission_number','first_name','last_name','date_of_birth','gender','grade_level','stream')}
    assert c.put(f"/api/admin/students/{students['Amina']}",headers=h['admin'],json={**payload,'stream':'Demo West'}).status_code==200
    register=c.get(f"/api/teacher/class-assignments/{past['assignment_id']}/register",headers=h['teacher']).json()
    assert next(r for r in register['recipients'] if r['student_id']==students['Amina'])['editable'] is False
    assert submit(audit,past['assignment_id'],[entry(audit)]).status_code==403
    assert len(report(audit)['assignments'])==2
    assert c.put(f"/api/admin/students/{students['Amina']}",headers=h['admin'],json=payload).status_code==200
    assert c.delete(f"/api/admin/students/{students['Amina']}",headers=h['admin']).status_code==200
    assert submit(audit,past['assignment_id'],[entry(audit)]).status_code==403
    newer=create(audit,title='New during absence',due_date='2026-11-18')
    assert c.patch(f"/api/admin/students/{students['Amina']}/status",headers=h['admin'],json={'is_archived':False}).status_code==200
    assert len(report(audit)['assignments'])==3
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(AssignmentCompletion).filter_by(student_id=students['Amina']))==3


def test_withdraw_restore_edit_and_deadline_guard(audit):
    c,h,_,students,sessions=audit
    row=create(audit);key=row['assignment_id'];base=f'/api/teacher/class-assignments/{key}'
    assert submit(audit,key,[{**entry(audit),'submitted_on':'2026-11-08','reason':None}]).status_code==200
    details={k:row[k] for k in ('title','instructions','assigned_date','due_date')}
    assert c.put(base,headers=h['teacher'],json={**details,'due_date':'2026-11-07'}).status_code==409
    assert c.put(base,headers=h['teacher'],json={**details,'grade_level':'Grade 8'}).status_code==422
    assert c.put(base,headers=h['teacher'],json={**details,'title':'Corrected title'}).status_code==200
    assert c.delete(base,headers=h['teacher']).status_code==200
    assert report(audit)['assignments']==[]
    assert report(audit)['completion_rate'] is None
    assert report(audit,include_withdrawn=True)['assignments'][0]['display_status']=='WITHDRAWN'
    assert submit(audit,key,[entry(audit)]).status_code==409
    assert c.patch(base+'/status',headers=h['teacher'],json={'is_withdrawn':False}).status_code==200
    assert report(audit)['counts']['SUBMITTED']==1
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(RecordChange).filter_by(entity_type='class_assignments',entity_id=key))==4


def test_assignment_permissions_validation_and_no_assessments(audit,monkeypatch):
    c,h,_,students,sessions=audit
    from app.services import analytics_service
    from app.services.catboost_service import ModelServiceError
    def broken(): raise ModelServiceError('No model available')
    monkeypatch.setattr(analytics_service,'get_catboost_service',broken)
    row=create(audit);key=row['assignment_id']
    assert report(audit,'David')['counts']['MISSING']==1  # No assessment records required.
    assert c.post('/api/teacher/class-assignments',headers=h['parent'],json=WORK).status_code==403
    assert c.post('/api/teacher/class-assignments',headers=h['teacher'],json={**WORK,'stream':'Demo West'}).status_code==403
    assert c.post('/api/teacher/class-assignments',headers=h['teacher'],json={**WORK,'subject_name':'Science'}).status_code==403
    assert c.post('/api/teacher/class-assignments',headers=h['teacher'],json={**WORK,'due_date':'2026-12-31','term':'Term 1'}).status_code==422
    assert c.get(f"/api/parent/children/{students['Brian']}/assignments",headers=h['parent'],params=PERIOD).status_code==403
    assert c.get(f'/api/teacher/class-assignments/{key}/register',headers=h['parent']).status_code==403
    assert c.get('/api/teacher/class-assignments/999999/register',headers=h['teacher']).status_code==404
    assert submit(audit,key,[{**entry(audit),'student_id':students['Esther']}]).status_code==400
    assert submit(audit,key,[{**entry(audit),'submitted_on':'2026-11-11'}]).status_code==400
    assert submit(audit,key,[{**entry(audit),'submitted_on':'2026-10-31'}]).status_code==400


def test_assignment_alert_preferences_dedup_and_resolution(audit):
    c,h,_,students,sessions=audit
    row=create(audit);key=row['assignment_id']
    def alerts():
        with sessions() as db:
            return db.scalars(select(Notification).where(Notification.dedup_key.like('assignment-followup:%'))).all()
    assert len(alerts())==2  # Linked Amina and David; no unlinked peers.
    assert c.post(f'/api/teacher/class-assignments/{key}/notify',headers=h['teacher']).status_code==200
    assert len(alerts())==2
    assert submit(audit,key,[entry(audit)]).status_code==200
    assert any('resolved' in a.title for a in alerts() if a.student_id==students['Amina'])
    assert c.put('/api/notifications/preferences',headers=h['parent'],json={'academic_updates':False}).status_code==200
    # Existing alerts remain history, but additional optional reminders are suppressed.
    before=len(alerts())
    create(audit,title='More work')
    assert len(alerts())==before


def test_reads_never_write_completion_or_send_alerts(audit,monkeypatch):
    c,h,_,_,sessions=audit
    row=create(audit,due_date='2026-11-10')
    with sessions() as db:
        notifications=db.scalar(select(func.count()).select_from(Notification))
        changes=db.scalar(select(func.count()).select_from(RecordChange))
    monkeypatch.setattr(service,'school_today',lambda:date(2026,11,12))
    assert report(audit)['counts']['MISSING']==1
    assert c.get(f"/api/teacher/class-assignments/{row['assignment_id']}/register",headers=h['teacher']).status_code==200
    with sessions() as db:
        assert notifications==db.scalar(select(func.count()).select_from(Notification))
        assert changes==db.scalar(select(func.count()).select_from(RecordChange))


@pytest.mark.parametrize("hour, expected", [(20, date(2026,11,9)),(21,date(2026,11,10))])
def test_nairobi_day_boundary(monkeypatch, hour, expected):
    class FrozenClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026,11,9,hour,5,tzinfo=timezone.utc).astimezone(tz)
    monkeypatch.setattr(service,'datetime',FrozenClock)
    assert REAL_SCHOOL_TODAY()==expected


def test_notification_failure_preserves_assignment_and_retry(audit,monkeypatch):
    from app.services.notification_service import NotificationService
    c,h,_,_,sessions=audit
    with monkeypatch.context() as temporary:
        def unavailable(*args,**kwargs): raise RuntimeError('Simulated notification failure')
        temporary.setattr(NotificationService,'send_notification',unavailable)
        row=create(audit)
        assert row['notification_delivery']['status']=='retry_needed'
        assert len(report(audit)['assignments'])==1
    result=c.post(f"/api/teacher/class-assignments/{row['assignment_id']}/notify",headers=h['teacher'])
    assert result.status_code==200 and result.json()['status']=='complete'


def test_fictional_assignment_seed_is_additive_and_preserves_changes(audit):
    from scripts.seed_assignments import seed_assignments
    c,h,_,students,sessions=audit
    with sessions() as db:
        keys=seed_assignments(db,'Term 3','2026')
        assert len(keys)==3
        first=db.get(ClassAssignment,keys[0])
        assert first.title.startswith('Demo:')
        completion=db.scalar(select(AssignmentCompletion).filter_by(assignment_id=keys[0],student_id=students['Amina']))
        completion.status='EXCUSED';completion.reason='Teacher correction';db.commit()
        before=db.scalar(select(func.count()).select_from(AssignmentCompletion))
        assert seed_assignments(db,'Term 3','2026')==keys
        assert db.scalar(select(func.count()).select_from(AssignmentCompletion))==before
        assert db.get(AssignmentCompletion,completion.completion_id).reason=='Teacher correction'
