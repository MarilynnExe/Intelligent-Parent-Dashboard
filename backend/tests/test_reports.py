"""School report denominators, read-only behavior, privacy and exports."""
import csv
import io
from datetime import date, datetime
import pytest
from sqlalchemy import select,func
from app.models.academic import Assessment
from app.models.analytics import AnalyticsFreshness, StudentAnalytics
from app.models.behaviour import Attendance
from app.models.competency import CompetencyObservation
from app.models.lifecycle import StudentLifecycle
from app.models.student import Student
from app.models.messaging import PrivateMessage
from app.models.notification import Notification
from app.services import assignment_service
from test_crud_audit import audit

PERIOD=dict(term='Term 3',academic_year='2026')
PATH='/api/admin/reports'
@pytest.fixture(autouse=True)
def today(monkeypatch):monkeypatch.setattr(assignment_service,'school_today',lambda:date(2026,11,10))
def report(audit,**params):
    c,h,_,_,_=audit
    r=c.get(PATH+'/overview',headers=h['admin'],params={**PERIOD,**params})
    assert r.status_code==200,r.text
    return r.json()
def export(audit,**params):
    c,h,_,_,_=audit
    r=c.get(PATH+'/export.csv',headers=h['admin'],params={**PERIOD,'dataset':'learners',**params})
    assert r.status_code==200,r.text
    return r,list(csv.DictReader(io.StringIO(r.content.decode('utf-8-sig'))))

def test_school_aggregate_means_coverage_no_assessment_zero(audit):
    data=report(audit);s=data['summary']
    assert s['learner_count']==5 and s['assessed_learners']==3 and s['unassessed_learners']==2
    assert s['academic_coverage_pct']==60 and s['academic_average']==63.33
    assert s['assessment_count']==12 and len(data['classes'])==2 and len(data['grades'])==1
    assert s['attendance_counts']=={'Present':15,'Late':0,'Absent':3,'Excused':0}
    assert s['attendance_rate_pct']==83.3 and s['recorded_learner_days']==18
    assert s['assignment_completion_pct'] is None and s['competency_coverage_pct'] is None
    assert len(data['subjects'])==2 and all(row['assessed_learners']==3 for row in data['subjects'])
    assert s['freshness_counts']=={'current':3,'stale':0,'pending':2,'unavailable':0}
    assert sum(s['support_counts'].values())==3
    david=next(row for row in data['learners']['items'] if row['student_name']=='David Demo')
    assert david['academic_average'] is None and david['attendance_rate_pct'] is None


def test_equal_learner_weight_and_previous_period_comparison(audit):
    c,h,users,students,sessions=audit
    with sessions() as db:
        db.add(Assessment(student_id=students['Amina'],subject_name='Mathematics',term='Term 3',academic_year='2026',assessment_type='Extra',score=100,max_score=100,percentage=100,assessment_date=date(2026,11,1),recorded_by_teacher_id=users['teacher']))
        db.add(Assessment(student_id=students['Amina'],subject_name='Mathematics',term='Term 2',academic_year='2026',assessment_type='Prior',score=20,max_score=100,percentage=20,assessment_date=date(2026,7,1),recorded_by_teacher_id=users['teacher']))
        db.commit()
    data=report(audit)
    assert data['summary']['academic_average']==67.67
    assert data['comparison']['term']=='Term 2' and data['comparison']['summary']['assessed_learners']==1
    assert data['comparison']['deltas']['academic_average']==47.67
    assert report(audit,compare_previous=False)['comparison'] is None
    prior=report(audit,term='Term 1')['comparison']
    assert prior['term']=='Term 3' and prior['academic_year']=='2025' and prior['deltas']['academic_average'] is None
    assert report(audit,term='Term 1',academic_year='0002')['comparison']['academic_year']=='0001'
    assert report(audit,term='Term 1',academic_year='0001')['comparison'] is None


def test_class_filter_archive_unknown_and_options(audit):
    c,h,_,students,sessions=audit
    assert report(audit,grade_level='Grade 7',stream='Demo East')['summary']['learner_count']==4
    assert report(audit,stream='Demo West')['summary']['learner_count']==1
    assert report(audit,grade_level='Missing')['summary']['learner_count']==0
    empty=report(audit,grade_level='Missing')
    assert empty['summary']['academic_average'] is None and empty['classes']==[] and empty['subjects']==[]
    with sessions() as db:db.add(StudentLifecycle(student_id=students['Amina'],is_archived=True));db.commit()
    s=report(audit)['summary'];assert s['learner_count']==4 and s['assessed_learners']==2 and s['academic_average']==77.5
    assert s['attendance_counts']['Absent']==0
    options=c.get(PATH+'/options',headers=h['admin']).json()['classes']
    assert len(options)==2
    with sessions() as db:
        db.get(Student,students['Esther']).stream=None
        db.get(Student,students['David']).stream=''
        db.commit()
    assert report(audit,stream='')['summary']['learner_count']==2
    options=c.get(PATH+'/options',headers=h['admin']).json()['classes']
    assert len([row for row in options if row['stream']==''])==1


def test_freshness_hides_old_support_and_invalid_current_snapshot(audit):
    _,_,_,students,sessions=audit
    with sessions() as db:
        db.get(AnalyticsFreshness,(students['Amina'],'Term 3','2026')).state='stale'
        db.get(AnalyticsFreshness,(students['Brian'],'Term 3','2026')).state='unavailable'
        row=db.scalar(select(StudentAnalytics).filter_by(student_id=students['Cynthia']))
        row.support_probability=None
        db.commit()
    data=report(audit)
    assert data['summary']['freshness_counts']=={'current':0,'stale':1,'pending':2,'unavailable':2}
    assert sum(data['summary']['support_counts'].values())==0
    assert all(row['support_status'] is None for row in data['learners']['items'])
    assert data['summary']['academic_average']==63.33


def test_assignment_and_competency_denominators_and_history(audit):
    from scripts.seed_assignments import seed_assignments
    from scripts.seed_competencies import seed_competencies
    c,h,_,students,sessions=audit
    with sessions() as db:
        seed_assignments(db,'Term 3','2026');seed_competencies(db,'Term 3','2026')
    data=report(audit);s=data['summary']
    assert s['assignment_recipient_count']==12 and s['due_count']==7 and s['completed_due_count']==3
    assert s['assignment_completion_pct']==42.9
    assert s['assignment_counts']=={'PENDING':4,'MISSING':4,'SUBMITTED':1,'LATE':2,'EXCUSED':1}
    assert s['competency_slots']==12 and s['assessed_competency_slots']==4
    assert s['competency_counts']['MEETING_EXPECTATIONS']==2 and s['competency_counts']['APPROACHING_EXPECTATIONS']==2
    assert s['competency_counts']['NOT_ASSESSED']==8 and s['competency_coverage_pct']==33.3
    assert report(audit,issue='missing_work')['learners']['total']==4
    assert report(audit,issue='competency_gaps')['learners']['total']==4
    with sessions() as db:
        db.get(Student,students['Amina']).stream='Demo West';db.commit()
    moved=report(audit,stream='Demo West')['summary']
    assert moved['competency_slots']==2 and moved['assessed_competency_slots']==2
    assert moved['assignment_recipient_count']==3


def test_attendance_excused_late_zero_denominator_and_months(audit):
    _,_,users,students,sessions=audit
    with sessions() as db:
        db.add_all([Attendance(student_id=students['David'],record_date=date(2026,10,1),status='Excused',recorded_by_teacher_id=users['teacher']),Attendance(student_id=students['David'],record_date=date(2026,11,1),status='Late',recorded_by_teacher_id=users['teacher'])]);db.commit()
    data=report(audit)
    assert data['summary']['attendance_denominator']==19
    assert data['summary']['recorded_learner_days']==20
    months={row['month']:row for row in data['attendance_trend']}
    assert months['2026-10']['attendance_rate_pct'] is None and months['2026-11']['attendance_rate_pct']==100


def test_learner_followup_filters_pagination_and_export_all_matches(audit):
    page=report(audit,issue='no_assessments',limit=1)
    assert page['learners']['total']==2 and len(page['learners']['items'])==1
    other=report(audit,issue='no_assessments',limit=1,offset=1)
    assert other['learners']['items'][0]['student_id']!=page['learners']['items'][0]['student_id']
    assert report(audit,issue='needs_calculation')['learners']['total']==2
    _,rows=export(audit,issue='no_assessments')
    assert len(rows)==2 and all(row['academic_average']=='' for row in rows)
    assert report(audit,issue='no_assessments',offset=100)['learners']['items']==[]


def test_export_csv_metadata_formula_safety_and_no_private_text(audit):
    from scripts.seed_messaging import seed_messaging
    c,h,_,students,sessions=audit
    with sessions() as db:
        seed_messaging(db)
        db.get(Student,students['Amina']).first_name='=HYPERLINK("bad")'
        db.get(Student,students['Amina']).admission_number='  +FORMULA'
        db.commit()
    response,rows=export(audit)
    row=next(r for r in rows if r['student_id']==str(students['Amina']))
    assert row['student_name'].startswith("'=") and row['admission_number'].startswith("'  +")
    assert 'private' not in response.text.lower() and 'fraction practice' not in response.text.lower()
    assert 'attachment' in response.headers['content-disposition'] and response.content.startswith(b'\xef\xbb\xbf')
    assert row['population_basis']=='current active enrollment' and row['academic_year']=='2026'
    for dataset in ['summary','grades','classes','subjects','attendance_trend']:
        _,items=export(audit,dataset=dataset);assert items
    _,items=export(audit,grade_level='No such grade');assert items==[]


def test_all_report_endpoints_are_admin_only(audit):
    c,h,_,_,_=audit
    for role in ['teacher','parent']:
        for endpoint,params in [('/options',{}),('/overview',PERIOD),('/export.csv',{**PERIOD,'dataset':'learners'})]:
            assert c.get(PATH+endpoint,headers=h[role],params=params).status_code==403

@pytest.mark.parametrize('changes',[{'term':'Term 4'},{'academic_year':'0000'},{'academic_year':'20266'},{'limit':0},{'limit':201},{'offset':-1},{'issue':'unknown'}])
def test_invalid_filters(audit,changes):
    c,h,_,_,_=audit
    assert c.get(PATH+'/overview',headers=h['admin'],params={**PERIOD,**changes}).status_code in (400,422)


def test_reports_do_not_write_or_recalculate(audit,monkeypatch):
    from app.services import analytics_service
    c,h,_,_,sessions=audit
    def forbidden(*args,**kwargs):raise AssertionError('Report must not calculate')
    monkeypatch.setattr(analytics_service,'calculate',forbidden)
    with sessions() as db:
        before={table.name:db.execute(select(func.count()).select_from(table)).scalar() for table in Student.metadata.sorted_tables}
        snapshots=[(r.analytics_id,r.support_probability,r.calculated_at) for r in db.scalars(select(StudentAnalytics))]
    for _ in range(2):report(audit)
    export(audit)
    with sessions() as db:
        assert before=={table.name:db.execute(select(func.count()).select_from(table)).scalar() for table in Student.metadata.sorted_tables}
        assert snapshots==[(r.analytics_id,r.support_probability,r.calculated_at) for r in db.scalars(select(StudentAnalytics))]
