"""Private messaging access, immutable sends, pagination and durable delivery."""
from uuid import uuid4
import pytest
from sqlalchemy import select, func
from app.models.messaging import Conversation, PrivateMessage
from app.models.notification import Notification, NotificationPreference
from app.models.student import ParentStudent, TeacherAssignment, Student
from app.models.lifecycle import StudentLifecycle, UserLifecycle, RecordChange
from app.models.user import User
from app.models.analytics import StudentAnalytics
from app.services import messaging_service as service
from test_crud_audit import audit

PREFIX='/api/messaging'
def start(audit, role='parent',student='Amina'):
    c,h,u,s,_=audit
    r=c.post(PREFIX+'/conversations',headers=h[role],json={'student_id':s[student],'contact_user_id':u['teacher' if role=='parent' else 'parent']})
    assert r.status_code==200,r.text
    return r.json()['conversation_id']
def send(audit,key,role='parent',body='Please review this classroom activity.',client=None):
    return audit[0].post(f'{PREFIX}/conversations/{key}/messages',headers=audit[1][role],json={'body':body,'client_message_id':client or str(uuid4())})
def history(audit,key,role='parent',**params):
    r=audit[0].get(f'{PREFIX}/conversations/{key}/messages',headers=audit[1][role],params=params)
    assert r.status_code==200,r.text
    return r.json()
def read(audit,key,message,role='teacher'):
    return audit[0].post(f'{PREFIX}/conversations/{key}/read',headers=audit[1][role],json={'through_message_id':message})

def test_contacts_initiation_dedup_and_private_text_no_analytics_change(audit):
    c,h,u,s,sessions=audit
    with sessions() as db:before=[(r.analytics_id,r.support_probability,r.calculated_at) for r in db.scalars(select(StudentAnalytics))]
    contacts=c.get(PREFIX+'/contacts',headers=h['parent'],params={'student_id':s['Amina']}).json()
    assert len(contacts)==1 and contacts[0]['user_id']==u['teacher']
    assert 'email_or_username' not in str(contacts)
    assert len(c.get(PREFIX+'/learners',headers=h['parent']).json())==2
    key=start(audit);assert start(audit,'teacher')==key
    text='<script>window.hacked=true</script> & plain text'
    result=send(audit,key,body='  '+text+'  ');assert result.status_code==200,result.text
    assert history(audit,key,'teacher')['items'][0]['body']==text
    assert send(audit,key,'teacher',body='Thank you for the update.').status_code==200
    with sessions() as db:
        assert before==[(r.analytics_id,r.support_probability,r.calculated_at) for r in db.scalars(select(StudentAnalytics))]
        assert db.scalar(select(func.count()).select_from(RecordChange).where(RecordChange.entity_type=='private_messages'))==0
        assert db.scalar(select(func.count()).select_from(Conversation))==1

def test_idempotent_retry_and_conflicting_identifier(audit):
    key=start(audit);client=str(uuid4())
    first=send(audit,key,client=client);second=send(audit,key,client=client)
    assert first.status_code==second.status_code==200
    assert first.json()['message_id']==second.json()['message_id'] and second.json()['duplicate']
    assert send(audit,key,client=client,body='Different content').status_code==409
    other=start(audit,student='David')
    assert send(audit,other,client=client).status_code==409
    assert len(history(audit,key)['items'])==1

def test_unread_and_partial_monotonic_read_cursors(audit):
    c,h,_,_,sessions=audit;key=start(audit)
    one=send(audit,key).json()['message_id'];two=send(audit,key,body='Second question').json()['message_id']
    listing=c.get(PREFIX+'/conversations',headers=h['teacher']).json()
    assert listing['unread_total']==2
    assert read(audit,key,one).status_code==200
    assert history(audit,key,'teacher')['conversation']['unread_count']==1
    with sessions() as db:assert not db.scalar(select(Notification).where(Notification.source_ref==f'messaging:{key}')).is_read
    assert read(audit,key,two).status_code==200
    assert read(audit,key,one).json()['unread_count']==0
    assert all(r['is_read'] for r in history(audit,key)['items'])
    with sessions() as db:assert db.scalar(select(Notification).where(Notification.source_ref==f'messaging:{key}')).is_read
    other=start(audit,student='David');foreign=send(audit,other).json()['message_id']
    assert read(audit,key,foreign).status_code==400
    assert read(audit,key,999999).status_code==400

def test_history_pagination_gets_have_no_read_side_effect(audit):
    key=start(audit)
    ids=[send(audit,key,body=f'Message {i}').json()['message_id'] for i in range(6)]
    page=history(audit,key,'teacher',limit=2)
    assert [r['message_id'] for r in page['items']]==ids[-2:] and page['has_older']
    older=history(audit,key,'teacher',limit=2,before_id=ids[-2])
    assert [r['message_id'] for r in older['items']]==ids[2:4]
    newer=history(audit,key,'teacher',limit=2,after_id=ids[0])
    assert [r['message_id'] for r in newer['items']]==ids[1:3] and newer['has_more']
    assert newer['conversation']['unread_count']==6
    c,h,_,_,_=audit
    assert c.get(f'{PREFIX}/conversations/{key}/messages',headers=h['teacher'],params={'before_id':1,'after_id':2}).status_code==400
    start(audit,student='David')
    pages=c.get(PREFIX+'/conversations',headers=h['parent'],params={'limit':1}).json()
    assert pages['has_more'] and len(pages['items'])==1
    assert len(c.get(PREFIX+'/conversations',headers=h['parent'],params={'limit':1,'offset':1}).json()['items'])==1

def test_admin_and_outsider_denied_all_messaging_routes(audit):
    c,h,u,s,sessions=audit;key=start(audit);mid=send(audit,key).json()['message_id']
    paths=[('GET','/learners',None),('GET',f'/contacts?student_id={s["Amina"]}',None),('GET','/conversations',None),('POST','/conversations',{'student_id':s['Amina'],'contact_user_id':u['teacher']}),('GET',f'/conversations/{key}/messages',None),('POST',f'/conversations/{key}/messages',{'body':'Denied','client_message_id':str(uuid4())}),('POST',f'/conversations/{key}/read',{'through_message_id':mid})]
    for method,path,payload in paths:
        assert c.request(method,PREFIX+path,headers=h['admin'],json=payload).status_code==403
    created=c.post('/api/admin/users',headers=h['admin'],json={'full_name':'Other Parent','email_or_username':'messages.other','password':'OtherPass2026!','role':'PARENT'})
    assert created.status_code==201
    login=c.post('/api/auth/login',json={'email_or_username':'messages.other','password':'OtherPass2026!'})
    outsider={'Authorization':'Bearer '+login.json()['access_token']}
    for method,path,payload in paths[-3:]:assert c.request(method,PREFIX+path,headers=outsider,json=payload).status_code==404
    assert c.get(PREFIX+'/conversations',headers=outsider).json()['items']==[]
    assert c.get(PREFIX+'/contacts',headers=h['parent'],params={'student_id':s['Brian']}).status_code==403
    assert c.post(PREFIX+'/conversations',headers=h['parent'],json={'student_id':s['Amina'],'contact_user_id':u['admin']}).status_code==403

@pytest.mark.parametrize('change',['unlink','unassign','transfer','archive','recipient_inactive','recipient_role'])
def test_access_changes_preserve_history_and_restore_replies(audit,change):
    c,h,u,s,sessions=audit;key=start(audit);mid=send(audit,key).json()['message_id']
    with sessions() as db:
        if change=='unlink':
            for row in db.scalars(select(ParentStudent).filter_by(parent_user_id=u['parent'],student_id=s['Amina'])):db.delete(row)
        elif change=='unassign':
            for row in db.scalars(select(TeacherAssignment).filter_by(teacher_user_id=u['teacher'])):db.delete(row)
        elif change=='transfer':db.get(Student,s['Amina']).stream='Demo West'
        elif change=='archive':db.add(StudentLifecycle(student_id=s['Amina'],is_archived=True))
        elif change=='recipient_inactive':db.add(UserLifecycle(user_id=u['teacher'],is_active=False,token_version=0))
        else:db.get(User,u['teacher']).role='PARENT'
        db.commit()
    data=history(audit,key)
    assert data['items'][0]['message_id']==mid and not data['conversation']['can_reply']
    assert send(audit,key).status_code==403
    assert read(audit,key,mid,role='parent').status_code==200
    with sessions() as db:
        if change=='unlink':db.add(ParentStudent(parent_user_id=u['parent'],student_id=s['Amina']))
        elif change=='unassign':db.add(TeacherAssignment(teacher_user_id=u['teacher'],grade_level='Grade 7',stream='Demo East',subject_name='Mathematics'))
        elif change=='transfer':db.get(Student,s['Amina']).stream='Demo East'
        elif change=='archive':db.get(StudentLifecycle,s['Amina']).is_archived=False
        elif change=='recipient_inactive':db.get(UserLifecycle,u['teacher']).is_active=True
        else:db.get(User,u['teacher']).role='TEACHER'
        db.commit()
    assert history(audit,key)['conversation']['can_reply']
    assert send(audit,key).status_code==200

def test_inactive_caller_session_blocked(audit):
    c,h,u,_,sessions=audit;key=start(audit)
    with sessions() as db:db.add(UserLifecycle(user_id=u['parent'],is_active=False,token_version=1));db.commit()
    assert c.get(f'{PREFIX}/conversations/{key}/messages',headers=h['parent']).status_code==401

@pytest.mark.parametrize('body',['   ','x'*4001])
def test_invalid_text_and_immutable_messages(audit,body):
    c,h,_,_,_=audit;key=start(audit)
    assert send(audit,key,body=body).status_code==422
    assert history(audit,key)['items']==[]
    row=send(audit,key,body='Valid text').json()
    for method in ['PUT','DELETE','PATCH']:
        assert c.request(method,f"{PREFIX}/conversations/{key}/messages/{row['message_id']}",headers=h['parent']).status_code in (404,405)

def test_generic_alert_preferences_and_new_alert_after_read(audit):
    c,h,u,_,sessions=audit;key=start(audit)
    assert send(audit,key,body='PRIVATE CONTENT MUST NOT APPEAR IN ALERT').status_code==200
    assert send(audit,key).status_code==200
    with sessions() as db:
        alerts=db.scalars(select(Notification).where(Notification.source_ref==f'messaging:{key}')).all()
        assert len(alerts)==1 and 'PRIVATE CONTENT' not in alerts[0].message
    latest=history(audit,key,'teacher')['items'][-1]['message_id'];assert read(audit,key,latest).status_code==200
    assert send(audit,key).status_code==200
    with sessions() as db:
        alerts=db.scalars(select(Notification).where(Notification.source_ref==f'messaging:{key}')).all()
        assert len(alerts)==2 and sum(not a.is_read for a in alerts)==1
        prefs=db.scalar(select(NotificationPreference).filter_by(user_id=u['teacher']))
        if not prefs:db.add(NotificationPreference(user_id=u['teacher'],notifications_enabled=False))
        else:prefs.notifications_enabled=False
        db.commit()
    key2=start(audit,student='David');assert send(audit,key2).status_code==200
    assert history(audit,key2,'teacher')['conversation']['unread_count']==1
    with sessions() as db:assert not db.scalar(select(Notification).where(Notification.source_ref==f'messaging:{key2}'))

def test_notification_failure_keeps_message_and_retry_recovers(audit,monkeypatch):
    key=start(audit);original=service.deliver_notification
    def unavailable(*args,**kwargs):raise RuntimeError('Notification unavailable')
    monkeypatch.setattr(service,'deliver_notification',unavailable)
    client=str(uuid4());r=send(audit,key,client=client)
    assert r.status_code==200 and r.json()['notification_delivery']['status']=='retry_needed'
    assert len(history(audit,key)['items'])==1
    monkeypatch.setattr(service,'deliver_notification',original)
    retry=send(audit,key,client=client)
    assert retry.status_code==200 and retry.json()['duplicate'] and retry.json()['notification_delivery']['status']=='complete'
    assert len(history(audit,key)['items'])==1

def test_concurrent_send_retry_and_alert_serialization_mysql(audit):
    from concurrent.futures import ThreadPoolExecutor
    with audit[4]() as db:
        if db.get_bind().dialect.name!='mysql':pytest.skip('Row-lock concurrency is verified on disposable MySQL.')
    key=start(audit);client=str(uuid4())
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses=list(pool.map(lambda _:send(audit,key,client=client),range(3)))
    assert all(r.status_code==200 for r in responses),[r.text for r in responses]
    assert len({r.json()['message_id'] for r in responses})==1
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses=list(pool.map(lambda i:send(audit,key,body=f'Concurrent message {i}'),range(3)))
    assert all(r.status_code==200 for r in responses),[r.text for r in responses]
    assert len(history(audit,key)['items'])==4
    with audit[4]() as db:
        alerts=db.scalars(select(Notification).where(Notification.source_ref==f'messaging:{key}',Notification.is_read.is_(False))).all()
        assert len(alerts)==1

def test_explicit_seed_is_repeatable_and_teacher_can_initiate(audit):
    from scripts.seed_messaging import seed_messaging
    c,h,u,s,sessions=audit
    key=start(audit,role='teacher',student='David')
    assert history(audit,key)['conversation']['can_reply']
    with sessions() as db:
        seeded=seed_messaging(db)
        count=db.scalar(select(func.count()).select_from(PrivateMessage))
        assert count==2 and seed_messaging(db)==seeded
        assert db.scalar(select(func.count()).select_from(PrivateMessage))==count
        assert db.scalar(select(func.count()).select_from(Conversation))==2
