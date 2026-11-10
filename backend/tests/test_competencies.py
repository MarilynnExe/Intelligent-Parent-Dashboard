from datetime import date
import pytest
from sqlalchemy import select
from app.models.analytics import StudentAnalytics
from app.models.competency import CompetencyObservation
from app.models.lifecycle import RecordChange
from app.models.notification import Notification, NotificationPreference
from app.models.student import Student
from app.services import assignment_service, competency_service
from test_crud_audit import audit

PERIOD=dict(term='Term 3',academic_year='2026')
SKILL=dict(grade_level='Grade 7',stream='Demo East',subject_name='Mathematics',name='Compare fractions',strand='Fractions',description='Explain fraction comparisons using diagrams.')
@pytest.fixture(autouse=True)
def today(monkeypatch):monkeypatch.setattr(assignment_service,'school_today',lambda:date(2026,11,10))
def create(audit,**changes):
    c,h,_,_,_=audit;r=c.post('/api/teacher/competencies',headers=h['teacher'],json={**SKILL,**changes})
    assert r.status_code==201,r.text
    return r.json()['competency_id']
def observe(audit,key,**changes):
    c,h,_,s,_=audit
    return c.post(f'/api/teacher/competencies/{key}/observations',headers=h['teacher'],json={**PERIOD,'student_id':s['Amina'],'observed_on':'2026-11-08','level':'APPROACHING_EXPECTATIONS','evidence':'Needs visual support for thirds.',**changes})
def report(audit,**params):
    c,h,_,s,_=audit;r=c.get(f"/api/parent/children/{s['Amina']}/competencies",headers=h['parent'],params={**PERIOD,**params})
    assert r.status_code==200,r.text
    return r.json()
def test_history_guidance_and_model_separation(audit):
    with audit[4]() as db:before=[(r.analytics_id,r.calculated_at,r.support_probability) for r in db.scalars(select(StudentAnalytics))]
    key=create(audit);assert report(audit)['counts']['NOT_ASSESSED']==1
    assert observe(audit,key).status_code==201
    assert report(audit)['guidance'][0]['rule_code']=='COMPETENCY_PRACTICE'
    assert observe(audit,key,observed_on='2026-11-09',level='MEETING_EXPECTATIONS').status_code==201
    data=report(audit);assert data['competencies'][0]['change']=='Improved' and len(data['competencies'][0]['history'])==2 and not data['guidance']
    assert report(audit,term='Term 2')['counts']['NOT_ASSESSED']==1
    with audit[4]() as db:assert before==[(r.analytics_id,r.calculated_at,r.support_probability) for r in db.scalars(select(StudentAnalytics))]
def test_crud_archive_restore_audit(audit):
    c,h,_,_,sessions=audit;key=create(audit);oid=observe(audit,key).json()['observation_id']
    assert c.put(f'/api/teacher/competencies/{key}',headers=h['teacher'],json={'name':'Explain fractions','strand':'Numbers','description':''}).status_code==200
    payload={**PERIOD,'observed_on':'2026-11-07','level':'BELOW_EXPECTATIONS','evidence':'Correction to original evidence.'}
    assert c.put(f'/api/teacher/competency-observations/{oid}',headers=h['teacher'],json=payload).status_code==200
    assert report(audit)['competencies'][0]['latest']['observed_on']=='2026-11-07'
    assert c.delete(f'/api/teacher/competencies/{key}',headers=h['teacher']).status_code==200
    assert report(audit)['competencies']==[] and observe(audit,key).status_code==409
    assert c.delete(f'/api/teacher/competency-observations/{oid}',headers=h['teacher']).status_code==409
    assert c.patch(f'/api/teacher/competencies/{key}/status',headers=h['teacher'],json={'is_archived':False}).status_code==200
    assert len(report(audit)['competencies'][0]['history'])==1
    assert c.delete(f'/api/teacher/competency-observations/{oid}',headers=h['teacher']).status_code==200
    assert report(audit)['counts']['NOT_ASSESSED']==1
    with sessions() as db:
        assert [r.action for r in db.scalars(select(RecordChange).filter_by(entity_type='competency_observations'))]==['create','update','delete']
        assert db.get(CompetencyObservation,oid) is None

def test_permissions_and_transfer_history(audit):
    c,h,_,s,sessions=audit
    assert c.post('/api/teacher/competencies',headers=h['teacher'],json={**SKILL,'stream':'Demo West'}).status_code==403
    key=create(audit);assert observe(audit,key,student_id=s['Esther']).status_code==403
    assert c.get(f"/api/parent/children/{s['Brian']}/competencies",headers=h['parent'],params=PERIOD).status_code==403
    assert observe(audit,key).status_code==201
    with sessions() as db:db.get(Student,s['Amina']).stream='Demo West';db.commit()
    assert observe(audit,key).status_code==403
    assert not report(audit)['competencies'][0]['current_class']
    register=c.get(f'/api/teacher/competencies/{key}/register',headers=h['teacher'],params=PERIOD).json()
    assert s['Amina'] not in [r['student_id'] for r in register['learners']]
@pytest.mark.parametrize('change',[{'observed_on':'2026-11-11'},{'observed_on':'2026-05-01'},{'academic_year':'2025'},{'evidence':'   '},{'level':'NOT_ASSESSED'},{'student_id':999999},{'evidence':'x'*2001},{'unknown':'value'}])
def test_invalid_evidence(audit,change):
    key=create(audit);assert observe(audit,key,**change).status_code in (400,404,422)
    assert report(audit)['counts']['NOT_ASSESSED']==1

def test_notification_preferences_dedup_resolution(audit):
    c,h,users,_,sessions=audit;key=create(audit)
    assert observe(audit,key).status_code==201 and observe(audit,key).status_code==201
    with sessions() as db:
        rows=db.scalars(select(Notification).filter_by(source_ref='competency_tracking')).all()
        assert len(rows)==1 and rows[0].recipient_user_id==users['parent'] and not rows[0].is_read
    assert observe(audit,key,level='MEETING_EXPECTATIONS',observed_on='2026-11-09').status_code==201
    with sessions() as db:
        assert db.scalar(select(Notification).filter_by(source_ref='competency_tracking')).is_read
        db.scalar(select(NotificationPreference).filter_by(user_id=users['parent'])).academic_updates=False;db.commit()
    assert observe(audit,create(audit,name='Equivalent fractions')).status_code==201
    with sessions() as db:assert len(db.scalars(select(Notification).filter_by(source_ref='competency_tracking')).all())==1

def test_notification_failure_preserves_evidence_and_retry(audit,monkeypatch):
    key=create(audit);original=competency_service.NotificationService.send_notification
    def unavailable(*args,**kwargs):raise RuntimeError('Unavailable')
    monkeypatch.setattr(competency_service.NotificationService,'send_notification',unavailable)
    r=observe(audit,key);assert r.status_code==201 and r.json()['notification_delivery']['status']=='retry_needed'
    assert report(audit)['counts']['APPROACHING_EXPECTATIONS']==1
    monkeypatch.setattr(competency_service.NotificationService,'send_notification',original)
    c,h,_,_,_=audit;r=c.post(f'/api/teacher/competencies/{key}/notify',headers=h['teacher'],params=PERIOD)
    assert r.status_code==200 and r.json()['status']=='complete'

def test_period_correction_updates_followups(audit):
    c,h,_,_,sessions=audit;key=create(audit);oid=observe(audit,key).json()['observation_id']
    r=c.put(f'/api/teacher/competency-observations/{oid}',headers=h['teacher'],json={**PERIOD,'term':'Term 2','observed_on':'2026-07-01','level':'BELOW_EXPECTATIONS','evidence':'Corrected period.'})
    assert r.status_code==200,r.text
    assert report(audit)['counts']['NOT_ASSESSED']==1 and report(audit,term='Term 2')['counts']['BELOW_EXPECTATIONS']==1
    with sessions() as db:
        rows=db.scalars(select(Notification).filter_by(source_ref='competency_tracking')).all()
        assert len(rows)==2 and sum(not r.is_read for r in rows)==1

def test_latest_date_ties_unassessed_without_academic_data_and_seed_repeat(audit):
    from scripts.seed_competencies import seed_competencies
    from app.models.competency import Competency
    c,h,_,s,sessions=audit
    with sessions() as db:
        ids=seed_competencies(db,'Term 3','2026')
        count=len(db.scalars(select(CompetencyObservation)).all())
        first=db.get(Competency,ids[0]);first.description='Teacher correction retained';db.commit()
        assert seed_competencies(db,'Term 3','2026')==ids
        assert db.get(Competency,ids[0]).description=='Teacher correction retained'
        assert len(db.scalars(select(CompetencyObservation)).all())==count
    r=c.get(f"/api/parent/children/{s['David']}/competencies",headers=h['parent'],params=PERIOD)
    assert r.status_code==200 and r.json()['counts']['NOT_ASSESSED']==1
    key=create(audit)
    assert observe(audit,key,observed_on='2026-11-09',level='MEETING_EXPECTATIONS').status_code==201
    assert observe(audit,key,observed_on='2026-11-08',level='BELOW_EXPECTATIONS').status_code==201
    item=next(i for i in report(audit)['competencies'] if i['competency_id']==key)
    assert item['latest']['level']=='MEETING_EXPECTATIONS'
    assert observe(audit,key,observed_on='2026-11-09',level='EXCEEDING_EXPECTATIONS').status_code==201
    item=next(i for i in report(audit)['competencies'] if i['competency_id']==key)
    assert item['latest']['level']=='EXCEEDING_EXPECTATIONS'

def test_archived_learner_and_removed_teacher_assignment_block_writes(audit):
    from app.models.lifecycle import StudentLifecycle
    from app.models.student import TeacherAssignment
    c,h,users,s,sessions=audit;key=create(audit)
    with sessions() as db:
        db.add(StudentLifecycle(student_id=s['Amina'],is_archived=True));db.commit()
    assert observe(audit,key).status_code==403
    assert c.get(f"/api/parent/children/{s['Amina']}/competencies",headers=h['parent'],params=PERIOD).status_code==403
    with sessions() as db:
        for row in db.scalars(select(TeacherAssignment).filter_by(teacher_user_id=users['teacher'])):db.delete(row)
        db.commit()
    assert c.get(f'/api/teacher/competencies/{key}/register',headers=h['teacher'],params=PERIOD).status_code==403
    assert observe(audit,key).status_code==403

def test_catalog_rename_refreshes_existing_followup(audit):
    c,h,_,_,sessions=audit;key=create(audit)
    assert observe(audit,key).status_code==201
    r=c.put(f'/api/teacher/competencies/{key}',headers=h['teacher'],json={'name':'New skill wording','strand':'Fractions','description':'Reworded rubric.'})
    assert r.status_code==200 and r.json()['notification_delivery']['status']=='complete'
    with sessions() as db:
        rows=db.scalars(select(Notification).filter_by(source_ref='competency_tracking')).all()
        assert len(rows)==1 and 'New skill wording' in rows[0].message
