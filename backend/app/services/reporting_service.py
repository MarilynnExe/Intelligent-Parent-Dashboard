"""Read-only school reporting over current active enrollment; no prediction calls."""
from collections import defaultdict, Counter
from datetime import datetime
import math
from app.core.academic_calendar import term_date_range
from app.models.academic import Assessment
from app.models.analytics import StudentAnalytics, AnalyticsFreshness
from app.models.behaviour import Attendance
from app.models.assignment import ClassAssignment, AssignmentCompletion
from app.models.competency import Competency, CompetencyObservation
from app.models.student import Student
from app.services import assignment_service
from app.services.lifecycle_service import active_students

LEVELS = ["BELOW_EXPECTATIONS", "APPROACHING_EXPECTATIONS", "MEETING_EXPECTATIONS", "EXCEEDING_EXPECTATIONS", "NOT_ASSESSED"]
SUPPORT = ["Targeted Support Recommended", "Monitoring Suggested", "On Track"]
STATES = ["current", "stale", "pending", "unavailable"]
METHODS = [
    "Population is current active enrollment, including historical periods; archived learners are excluded. Historical enrollment is not available.",
    "Academic means give each assessed learner equal weight; each learner's mean uses their recorded assessment percentages. Missing assessments are not zero scores.",
    "Attendance rate is (Present + Late) / (Present + Late + Absent) recorded learner-days. Excused and unrecorded days are excluded; no official school-day coverage is inferred.",
    "Assignment completion counts submitted recipient records for work due by the report date, excluding excused and withdrawn work; late submissions count as complete. Retained work follows its recipient's current class for grouping.",
    "Competency coverage is assessed learner-skill slots / eligible learner-skill slots. Active current-class skills plus observed previous-class skills are included; latest date and observation ID determine each level. The catalog is current and teacher-defined, not verified official curriculum coverage.",
    "Support totals include only current stored analytics with a valid probability and calculation timestamp. Reports never calculate predictions or expose private messages or teacher evidence text.",
    "Previous-period comparisons use the same current learner population; assessment coverage, assigned work and recorded attendance can differ. Changes are descriptive, not causal evidence of progress.",
]

def rate(numerator, denominator):
    return round(100 * numerator / denominator, 1) if denominator else None

def mean(values):
    return round(sum(values) / len(values), 2) if values else None

def blank(student):
    return {"student_id": student.student_id, "admission_number": student.admission_number,
        "student_name": f"{student.first_name} {student.last_name}", "grade_level": student.grade_level,
        "stream": student.stream or "", "assessment_count": 0, "academic_average": None,
        "attendance_counts": {s: 0 for s in ["Present", "Late", "Absent", "Excused"]},
        "assignment_counts": {s: 0 for s in ["PENDING", "MISSING", "SUBMITTED", "LATE", "EXCUSED"]},
        "due_count": 0, "completed_due_count": 0, "assignment_recipient_count": 0,
        "competency_counts": {s: 0 for s in LEVELS}, "freshness": "pending", "calculated_at": None,
        "support_status": None}

def aggregate(rows):
    attendance = {s: sum(row["attendance_counts"][s] for row in rows) for s in ["Present", "Late", "Absent", "Excused"]}
    assignments = {s: sum(row["assignment_counts"][s] for row in rows) for s in ["PENDING", "MISSING", "SUBMITTED", "LATE", "EXCUSED"]}
    competencies = {s: sum(row["competency_counts"][s] for row in rows) for s in LEVELS}
    learner_count = len(rows)
    assessed = [row["academic_average"] for row in rows if row["academic_average"] is not None]
    due = sum(row["due_count"] for row in rows)
    completed = sum(row["completed_due_count"] for row in rows)
    expected = sum(competencies.values())
    competency_assessed = expected - competencies["NOT_ASSESSED"]
    recorded_days = sum(attendance.values())
    attendance_denominator = attendance["Present"] + attendance["Late"] + attendance["Absent"]
    return {"learner_count": learner_count, "assessed_learners": len(assessed),
        "unassessed_learners": learner_count-len(assessed), "academic_coverage_pct": rate(len(assessed), learner_count),
        "assessment_count": sum(row["assessment_count"] for row in rows), "academic_average": mean(assessed),
        "attendance_counts": attendance, "recorded_learner_days": recorded_days,
        "learners_with_attendance": sum(bool(sum(row["attendance_counts"].values())) for row in rows),
        "attendance_denominator": attendance_denominator,
        "attendance_rate_pct": rate(attendance["Present"]+attendance["Late"], attendance_denominator),
        "assignment_counts": assignments, "assignment_recipient_count": sum(row["assignment_recipient_count"] for row in rows),
        "learners_with_assignments": sum(row["assignment_recipient_count"]>0 for row in rows),
        "due_count": due, "completed_due_count": completed, "assignment_completion_pct": rate(completed,due),
        "competency_counts": competencies, "competency_slots": expected, "assessed_competency_slots": competency_assessed,
        "competency_coverage_pct": rate(competency_assessed,expected),
        "learners_with_competency_evidence": sum(sum(row["competency_counts"][s] for s in LEVELS[:-1])>0 for row in rows),
        "freshness_counts": {s: sum(row["freshness"]==s for row in rows) for s in STATES},
        "support_counts": {s: sum(row["support_status"]==s for row in rows) for s in SUPPORT},
        "analytics_coverage_pct": rate(sum(row["freshness"]=="current" for row in rows),learner_count)}

def previous_period(term, year):
    index = ["Term 1", "Term 2", "Term 3"].index(term)
    if index: return f"Term {index}", year
    return "Term 3", str(int(year)-1).zfill(4)

def period_report(db, students, term, year, today):
    start,end = term_date_range(term,year)
    profiles = {s.student_id: blank(s) for s in students}
    ids = set(profiles)
    # Source records are fetched in batches, rather than one query per learner.
    def selected(query, student_column):
        return query.join(Student, Student.student_id==student_column).filter(active_students(),
            Student.student_id.in_(ids))
    # Restrict sources to the captured population even if enrollment changes.
    # No calculation service or write runs on a GET.
    assessments = selected(db.query(Assessment), Assessment.student_id).filter(Assessment.term==term, Assessment.academic_year==year).all() if ids else []
    marks = defaultdict(list); subjects = defaultdict(lambda:defaultdict(list))
    for row in assessments:
        marks[row.student_id].append(row.percentage)
        subjects[row.subject_name][row.student_id].append(row.percentage)
    for sid, values in marks.items():
        profiles[sid]["assessment_count"], profiles[sid]["academic_average"] = len(values), mean(values)
    attendance = selected(db.query(Attendance), Attendance.student_id).filter(Attendance.record_date>=start, Attendance.record_date<=end).all() if ids else []
    monthly = defaultdict(Counter)
    for row in attendance:
        if row.status in profiles[row.student_id]["attendance_counts"]:
            profiles[row.student_id]["attendance_counts"][row.status] += 1
            monthly[row.record_date.strftime("%Y-%m")][row.status] += 1
    work = selected(db.query(ClassAssignment, AssignmentCompletion).join(AssignmentCompletion,
        AssignmentCompletion.assignment_id==ClassAssignment.assignment_id),AssignmentCompletion.student_id).filter(
        ClassAssignment.term==term,ClassAssignment.academic_year==year,ClassAssignment.is_withdrawn.is_(False)).all() if ids else []
    for assignment,entry in work:
        profile=profiles[entry.student_id]
        profile["assignment_recipient_count"]+=1
        profile["assignment_counts"][assignment_service.display_status(assignment,entry,today)]+=1
        if assignment.due_date<=today and entry.status!="EXCUSED":
            profile["due_count"]+=1
            profile["completed_due_count"]+=entry.status=="SUBMITTED"
    catalog=db.query(Competency).filter_by(is_archived=False).all() if ids else []
    by_class=defaultdict(set); skill_ids=set()
    for skill in catalog:
        by_class[(skill.grade_level,skill.stream or "")].add(skill.competency_id)
        skill_ids.add(skill.competency_id)
    observations=selected(db.query(CompetencyObservation), CompetencyObservation.student_id).filter(
        CompetencyObservation.term==term,CompetencyObservation.academic_year==year).order_by(
        CompetencyObservation.observed_on,CompetencyObservation.observation_id).all() if ids else []
    latest=defaultdict(dict)
    for row in observations:
        if row.competency_id in skill_ids: latest[row.student_id][row.competency_id]=row.level
    for sid,profile in profiles.items():
        eligible=by_class[(profile["grade_level"],profile["stream"])] | set(latest[sid])
        for skill_id in eligible:
            level=latest[sid].get(skill_id,"NOT_ASSESSED")
            profile["competency_counts"][level]+=1
    snapshots = selected(db.query(StudentAnalytics),StudentAnalytics.student_id).filter(
        StudentAnalytics.term==term,StudentAnalytics.academic_year==year).order_by(
        StudentAnalytics.calculated_at,StudentAnalytics.analytics_id).all() if ids else []
    snapshots={row.student_id:row for row in snapshots}
    freshness=selected(db.query(AnalyticsFreshness),AnalyticsFreshness.student_id).filter(
        AnalyticsFreshness.term==term,AnalyticsFreshness.academic_year==year).all() if ids else []
    freshness={row.student_id:row for row in freshness}
    for sid,profile in profiles.items():
        snapshot, fresh=snapshots.get(sid),freshness.get(sid)
        state=fresh.state if fresh else "stale" if snapshot else "pending"
        if state not in STATES: state="unavailable"
        if state=="current":
            valid=bool(snapshot and snapshot.calculated_at and snapshot.support_probability is not None
                and math.isfinite(snapshot.support_probability) and 0<=snapshot.support_probability<=1
                and snapshot.support_status in SUPPORT and profile["assessment_count"])
            if not valid: state="unavailable"
        profile["freshness"]=state
        profile["calculated_at"]=snapshot.calculated_at if snapshot else None
        profile["support_status"]=snapshot.support_status if state=="current" else None
        counts=profile["attendance_counts"]
        profile["attendance_rate_pct"]=rate(counts["Present"]+counts["Late"],counts["Present"]+counts["Late"]+counts["Absent"])
        profile["assignment_completion_pct"]=rate(profile["completed_due_count"],profile["due_count"])
        expected=sum(profile["competency_counts"].values())
        profile["competency_coverage_pct"]=rate(expected-profile["competency_counts"]["NOT_ASSESSED"],expected)
    rows=list(profiles.values())
    classes=defaultdict(list); grades=defaultdict(list)
    for row in rows:
        classes[(row["grade_level"],row["stream"])].append(row)
        grades[row["grade_level"]].append(row)
    return {"summary":aggregate(rows), "grades":[{"grade_level":grade,**aggregate(items)} for grade,items in sorted(grades.items())],
        "classes":[{"grade_level":grade,"stream":stream,**aggregate(items)} for (grade,stream),items in sorted(classes.items())],
        "subjects":[{"subject_name":subject,"assessed_learners":len(values),
            "assessment_count":sum(len(v) for v in values.values()), "academic_average":mean([mean(v) for v in values.values()])}
            for subject,values in sorted(subjects.items())],
        "attendance_trend":[{"month":month, "counts":{s:counts[s] for s in ["Present","Late","Absent","Excused"]},
            "attendance_rate_pct":rate(counts["Present"]+counts["Late"],counts["Present"]+counts["Late"]+counts["Absent"])}
            for month,counts in sorted(monthly.items())], "learners":rows}

def report(db, term, year, grade_level=None, stream=None, compare_previous=True):
    query=db.query(Student).filter(active_students())
    if grade_level is not None: query=query.filter(Student.grade_level==grade_level)
    if stream is not None:
        if stream:query=query.filter(Student.stream==stream)
        else:query=query.filter((Student.stream.is_(None)) | (Student.stream==""))
    students=query.order_by(Student.grade_level,Student.stream,Student.first_name,Student.student_id).all()
    today=assignment_service.school_today()
    result=period_report(db,students,term,year,today)
    result.update({"term":term,"academic_year":year,"as_of":today,
        "generated_at":datetime.utcnow(),"filters":{"grade_level":grade_level,"stream":stream},"methodology":METHODS})
    result["comparison"]=None
    if compare_previous and not (term=="Term 1" and year=="0001"):
        prior_term,prior_year=previous_period(term,year)
        prior=period_report(db,students,prior_term,prior_year,today)["summary"]
        keys=["academic_average","academic_coverage_pct","attendance_rate_pct","assignment_completion_pct","competency_coverage_pct","analytics_coverage_pct"]
        result["comparison"]={"term":prior_term,"academic_year":prior_year,"summary":prior,
            "deltas":{key:round(result["summary"][key]-prior[key],2) if result["summary"][key] is not None and prior[key] is not None else None for key in keys}}
    return result

def matches_issue(row, issue):
    return (issue=="all" or issue=="needs_calculation" and row["freshness"]!="current"
        or issue=="no_assessments" and not row["assessment_count"]
        or issue=="missing_work" and row["assignment_counts"]["MISSING"]>0
        or issue=="competency_gaps" and row["competency_counts"]["NOT_ASSESSED"]>0)
