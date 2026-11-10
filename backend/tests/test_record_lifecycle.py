"""Corrections, audit history, lifecycle, and dependent analytics on SQLite/MySQL."""
from sqlalchemy import select, func
from app.models.academic import Assessment
from app.models.behaviour import Attendance, BehaviourRecord, TeacherObservation
from app.models.lifecycle import RecordChange
from app.models.user import User
from test_crud_audit import audit, PERIOD


def test_user_edit_password_reset_deactivate_and_restore(audit):
    c, h, users, _, sessions = audit
    parent = next(u for u in c.get('/api/admin/users', headers=h['admin']).json() if u['user_id'] == users['parent'])
    payload = {k:parent[k] for k in ('full_name','email_or_username','role','phone_number')}
    payload.update(full_name='Corrected Parent', password=None)
    result = c.put(f"/api/admin/users/{users['parent']}", headers=h['admin'], json=payload)
    assert result.status_code == 200, result.text
    assert c.get('/api/auth/me', headers=h['parent']).json()['full_name'] == 'Corrected Parent'
    payload['password'] = 'CorrectedPass2026!'
    assert c.put(f"/api/admin/users/{users['parent']}", headers=h['admin'], json=payload).status_code == 200
    assert c.get('/api/auth/me', headers=h['parent']).status_code == 401
    login = c.post('/api/auth/login', json=dict(email_or_username='demo.parent', password=payload['password']))
    token = {'Authorization':'Bearer '+login.json()['access_token']}
    assert c.delete(f"/api/admin/users/{users['parent']}", headers=h['admin']).status_code == 200
    assert c.get('/api/auth/me', headers=token).status_code == 401
    assert c.post('/api/auth/login', json=dict(email_or_username='demo.parent', password=payload['password'])).status_code == 401
    assert c.patch(f"/api/admin/users/{users['parent']}/status", headers=h['admin'], json={'is_active':True}).status_code == 200
    assert c.get('/api/auth/me', headers=token).status_code == 401  # Old sessions stay revoked after restore.
    assert c.post('/api/auth/login', json=dict(email_or_username='demo.parent', password=payload['password'])).status_code == 200
    with sessions() as db:
        history = db.scalars(select(RecordChange).filter_by(entity_type='users', entity_id=users['parent'])).all()
        assert len(history) == 4
        assert all('password' not in (r.before_json or '') + (r.after_json or '') for r in history)


def test_admin_guards_and_duplicate_user_edit(audit):
    c, h, users, _, _ = audit
    assert c.delete(f"/api/admin/users/{users['admin']}", headers=h['admin']).status_code == 409
    user = c.get('/api/auth/me', headers=h['admin']).json()
    assert c.put(f"/api/admin/users/{users['admin']}", headers=h['admin'], json={**user,'role':'PARENT','password':None}).status_code == 409
    user = c.get('/api/auth/me', headers=h['teacher']).json()
    assert c.put(f"/api/admin/users/{users['teacher']}", headers=h['admin'], json={**user,'role':'PARENT','password':None}).status_code == 409
    assert c.put(f"/api/admin/users/{users['teacher']}", headers=h['admin'], json={**user,'email_or_username':'demo.parent','password':None}).status_code == 409
    assert c.put('/api/admin/users/999999', headers=h['admin'], json={**user,'password':None}).status_code == 404


def test_student_edit_move_archive_restore_and_duplicate(audit):
    c, h, _, students, sessions = audit
    row = next(s for s in c.get('/api/admin/students', headers=h['admin']).json() if s['student_id'] == students['Amina'])
    payload = {k:row[k] for k in ('admission_number','first_name','last_name','date_of_birth','gender','grade_level','stream')}
    payload.update(first_name='Corrected',stream='Demo West')
    result = c.put(f"/api/admin/students/{students['Amina']}", headers=h['admin'], json=payload)
    assert result.status_code == 200, result.text
    roster = c.get('/api/teacher/students', headers=h['teacher'], params=dict(grade_level='Grade 7',stream='Demo East')).json()
    assert all(s['student_id'] != students['Amina'] for s in roster)
    assert c.get(f"/api/teacher/students/{students['Amina']}/assessments", headers=h['teacher']).status_code == 403
    peer = c.get(f"/api/analytics/student/{students['Brian']}",headers=h['admin'],params=PERIOD).json()
    assert peer['is_current'] and peer['cohort_percentile'] == 25.0
    assert c.get(f"/api/analytics/student/{students['Amina']}", headers=h['parent'], params=PERIOD).json()['is_current'] is True
    assert c.put(f"/api/admin/students/{students['Amina']}", headers=h['admin'], json={**payload,'admission_number':'DEMO-002'}).status_code == 409
    assert c.delete(f"/api/admin/students/{students['Amina']}", headers=h['admin']).status_code == 200
    assert all(s['student_id'] != students['Amina'] for s in c.get('/api/parent/my-children',headers=h['parent']).json())
    assert c.get(f"/api/analytics/student/{students['Amina']}", headers=h['parent']).status_code == 403
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Assessment).filter_by(student_id=students['Amina'])) == 4
    assert c.patch(f"/api/admin/students/{students['Amina']}/status", headers=h['admin'], json={'is_archived':False}).status_code == 200
    assert c.get(f"/api/parent/children/{students['Amina']}/progress", headers=h['parent'], params=PERIOD).json()['freshness'] == 'current'


def test_assignment_and_parent_link_edit_revoke_previous_access(audit):
    c, h, users, students, _ = audit
    assignments = c.get('/api/admin/teacher-assignments',headers=h['admin']).json()
    row = assignments[0]
    result = c.put(f"/api/admin/teacher-assignments/{row['assignment_id']}",headers=h['admin'],json={**row,'stream':'Demo West'})
    assert result.status_code == 200, result.text
    assert c.get('/api/teacher/students',headers=h['teacher'],params=dict(grade_level='Grade 7',stream='Demo West')).status_code == 200
    assert c.put(f"/api/admin/teacher-assignments/{row['assignment_id']}",headers=h['admin'],json=assignments[1]).status_code == 409
    link = next(r for r in c.get('/api/admin/parent-links',headers=h['admin']).json() if r['student_id'] == students['Amina'])
    result = c.put(f"/api/admin/parent-links/{link['id']}",headers=h['admin'],json={**link,'student_id':students['Brian'],'relationship_type':'Father'})
    assert result.status_code == 200, result.text
    assert c.get(f"/api/parent/children/{students['Amina']}/progress",headers=h['parent'],params=PERIOD).status_code == 403
    assert c.get(f"/api/parent/children/{students['Brian']}/progress",headers=h['parent'],params=PERIOD).status_code == 200
    assert c.put(f"/api/admin/parent-links/{link['id']}",headers=h['admin'],json={**link,'student_id':students['David']}).status_code == 409


def test_assessment_correct_term_delete_last_and_history(audit):
    c, h, _, students, sessions = audit
    with sessions() as db:
        rows = db.scalars(select(Assessment).filter_by(student_id=students['Amina'])).all()
        row = rows[0]
        key = row.assessment_id
        payload = dict(student_id=row.student_id,subject_name=row.subject_name,term='Term 2',academic_year='2026',assessment_type='CAT',score=90,max_score=100,assessment_date='2026-05-20')
    result = c.put(f'/api/teacher/assessments/{key}',headers=h['teacher'],json=payload)
    assert result.status_code == 200, result.text
    assert set(result.json()['analytics_refresh']) == {'Term 3 2026','Term 2 2026'}
    assert c.get(f"/api/analytics/student/{students['Amina']}",headers=h['parent'],params=dict(term='Term 2',academic_year='2026')).json()['overall_average'] == 90
    assert c.put(f'/api/teacher/assessments/{key}',headers=h['teacher'],json={**payload,'score':101}).status_code == 400
    assert c.put(f'/api/teacher/assessments/{key}',headers=h['teacher'],json={**payload,'student_id':students['Brian']}).status_code == 400
    assert c.delete(f'/api/teacher/assessments/{key}',headers=h['parent']).status_code == 403
    assert c.delete(f'/api/teacher/assessments/{key}',headers=h['teacher']).status_code == 200
    stored = c.get(f"/api/analytics/student/{students['Amina']}",headers=h['parent'],params=dict(term='Term 2',academic_year='2026')).json()
    assert stored['is_current'] is False and stored['support_probability'] is None and stored['freshness'] == 'pending'
    assert c.delete(f'/api/teacher/assessments/{key}',headers=h['teacher']).status_code == 404
    history = c.get('/api/admin/change-history',headers=h['admin'],params=dict(entity_type='assessments',entity_id=key))
    assert history.status_code == 200 and len(history.json()) == 2
    assert c.get('/api/admin/change-history',headers=h['teacher'],params=dict(entity_type='assessments',entity_id=key)).status_code == 403


def test_behaviour_observation_edit_delete_and_class_security(audit):
    c, h, _, students, sessions = audit
    with sessions() as db:
        key = db.scalar(select(BehaviourRecord).filter_by(student_id=students['Amina'])).record_id
    payload = dict(student_id=students['Amina'],category='Engagement',rating=5,record_date='2026-09-11',teacher_note='Corrected rating')
    assert c.put(f'/api/teacher/behaviour/{key}',headers=h['teacher'],json=payload).status_code == 200
    analytics = c.get(f"/api/analytics/student/{students['Amina']}",headers=h['parent'],params=PERIOD).json()
    assert 'BEHAV_ATTENTION_REQUIRED' not in {r['rule_code'] for r in analytics['recommendations']}
    assert c.delete(f'/api/teacher/behaviour/{key}',headers=h['teacher']).status_code == 200
    assert c.get(f"/api/teacher/students/{students['Amina']}/behaviour",headers=h['teacher']).json() == []
    payload = dict(student_id=students['Amina'],**PERIOD,observation_text='Original',observation_date='2026-09-20')
    assert c.post('/api/teacher/observations',headers=h['teacher'],json=payload).status_code == 200
    key = c.get(f"/api/teacher/students/{students['Amina']}/observations",headers=h['teacher']).json()[0]['observation_id']
    assert c.put(f'/api/teacher/observations/{key}',headers=h['teacher'],json={**payload,'observation_text':'Corrected'}).status_code == 200
    assert c.delete(f'/api/teacher/observations/{key}',headers=h['teacher']).status_code == 200
    # Moving the student's class revokes teacher correction/delete access to the preserved records.
    with sessions() as db:
        from app.models.student import Student
        db.get(Student,students['Amina']).stream='Demo West';db.commit()
    assert c.delete(f"/api/teacher/assessments/{1}",headers=h['teacher']).status_code == 403


def test_saved_attendance_load_correct_delete(audit):
    c, h, _, students, _ = audit
    query = dict(grade_level='Grade 7',stream='Demo East',record_date='2026-09-06')
    loaded = c.get('/api/teacher/attendance',headers=h['teacher'],params=query)
    assert loaded.status_code == 200, loaded.text
    row = next(r for r in loaded.json() if r['student_id'] == students['Amina'])
    assert row['status'] == 'Absent'
    assert c.get('/api/teacher/attendance',headers=h['parent'],params=query).status_code == 403
    assert c.get('/api/teacher/attendance',headers=h['teacher'],params={**query,'stream':'Demo West'}).status_code == 403
    assert c.post('/api/teacher/attendance/bulk',headers=h['teacher'],json=dict(record_date=query['record_date'],entries=[dict(student_id=students['Amina'],status='Excused',remarks='Correction')])).status_code == 200
    row2 = next(r for r in c.get('/api/teacher/attendance',headers=h['teacher'],params=query).json() if r['student_id']==students['Amina'])
    assert row2['status'] == 'Excused' and row2['attendance_id'] == row['attendance_id']
    assert c.delete(f"/api/teacher/attendance/{row['attendance_id']}",headers=h['teacher']).status_code == 200
    assert all(r['student_id'] != students['Amina'] for r in c.get('/api/teacher/attendance',headers=h['teacher'],params=query).json())
    assert c.get('/api/teacher/attendance',headers=h['teacher'],params={**query,'record_date':'2025-01-01'}).json() == []


def test_correction_model_failure_preserves_changes_and_audit(audit,monkeypatch):
    c,h,_,students,sessions=audit
    from app.services import analytics_service
    from app.services.catboost_service import ModelServiceError
    def broken(): raise ModelServiceError('Simulated failure')
    monkeypatch.setattr(analytics_service,'get_catboost_service',broken)
    row=c.get(f"/api/teacher/students/{students['Amina']}/assessments",headers=h['teacher']).json()[0]
    result=c.put(f"/api/teacher/assessments/{row['assessment_id']}",headers=h['teacher'],json={**row,'score':99})
    assert result.status_code==200
    with sessions() as db:
        assert db.get(Assessment,row['assessment_id']).score==99
        assert db.scalar(select(func.count()).select_from(RecordChange).filter_by(entity_type='assessments'))==1
    result=c.get(f"/api/analytics/student/{students['Amina']}",headers=h['parent'],params=PERIOD).json()
    assert not result['is_current'] and result['support_probability'] is None


def test_subject_permission_required_for_assessment_corrections(audit):
    c,h,_,students,_=audit
    assignments=c.get('/api/admin/teacher-assignments',headers=h['admin']).json()
    english=next(a for a in assignments if a['subject_name']=='English')
    assert c.delete(f"/api/admin/teacher-assignments/{english['assignment_id']}",headers=h['admin']).status_code==200
    rows=c.get(f"/api/teacher/students/{students['Amina']}/assessments",headers=h['teacher']).json()
    english=next(a for a in rows if a['subject_name']=='English')
    maths=next(a for a in rows if a['subject_name']=='Mathematics')
    assert c.delete(f"/api/teacher/assessments/{english['assessment_id']}",headers=h['teacher']).status_code==403
    assert c.put(f"/api/teacher/assessments/{maths['assessment_id']}",headers=h['teacher'],json={**maths,'subject_name':'English'}).status_code==403


def test_inactive_accounts_and_archived_learners_cannot_get_new_links(audit):
    c,h,users,students,_=audit
    assert c.delete(f"/api/admin/users/{users['teacher']}",headers=h['admin']).status_code==200
    assert c.post('/api/admin/teacher-assignments',headers=h['admin'],json=dict(teacher_user_id=users['teacher'],grade_level='Grade 8',stream='East',subject_name='Mathematics')).status_code==400
    assert c.delete(f"/api/admin/students/{students['Brian']}",headers=h['admin']).status_code==200
    assert c.post('/api/admin/parent-links',headers=h['admin'],json=dict(parent_user_id=users['parent'],student_id=students['Brian'])).status_code==403
