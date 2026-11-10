"""Administrator-only read-only reporting and spreadsheet-safe CSV exports."""
import csv
import io
from typing import Literal
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import require_role
from app.models.student import Student
from app.services.lifecycle_service import active_students
from app.services import reporting_service as service

router=APIRouter(prefix="/admin/reports", tags=["School Reports"])
admin=require_role(["ADMIN"])
Issue=Literal["all","needs_calculation","no_assessments","missing_work","competency_gaps"]
Dataset=Literal["summary","grades","classes","subjects","learners","attendance_trend"]

@router.get("/options")
def options(actor=Depends(admin),db: Session=Depends(get_db)):
    rows=db.query(Student.grade_level,Student.stream).filter(active_students()).distinct().all()
    classes=sorted({(grade,stream or "") for grade,stream in rows})
    return {"classes":[{"grade_level":grade,"stream":stream} for grade,stream in classes]}

@router.get("/overview")
def overview(term: Literal["Term 1","Term 2","Term 3"], academic_year: str=Query(pattern=r"^[0-9]{4}$"),
    grade_level: str | None=Query(None,max_length=50),stream: str | None=Query(None,max_length=50),
    compare_previous: bool=True, issue: Issue="all", limit: int=Query(50,ge=1,le=200),offset: int=Query(0,ge=0),
    actor=Depends(admin),db: Session=Depends(get_db)):
    if int(academic_year)==0:raise HTTPException(status_code=400,detail="Academic year must be between 0001 and 9999.")
    result=service.report(db,term,academic_year,grade_level,stream,compare_previous)
    learners=[row for row in result.pop("learners") if service.matches_issue(row,issue)]
    result["learners"]={"items":learners[offset:offset+limit],"total":len(learners),"limit":limit,"offset":offset,"issue":issue}
    return result

def flatten(row,prefix=""):
    result={}
    for key,value in row.items():
        name=f"{prefix}{key}"
        if isinstance(value,dict):result.update(flatten(value,name+"_"))
        else:result[name]=value
    return result

def safe_cell(value):
    if isinstance(value,str) and (value.startswith(("\t","\r","\n")) or value.lstrip().startswith(("=","+","-","@"))):
        return "'"+value
    return value

@router.get("/export.csv")
def export(dataset: Dataset, term: Literal["Term 1","Term 2","Term 3"],academic_year: str=Query(pattern=r"^[0-9]{4}$"),
    grade_level: str | None=Query(None,max_length=50),stream: str | None=Query(None,max_length=50),issue: Issue="all",
    actor=Depends(admin),db: Session=Depends(get_db)):
    if int(academic_year)==0:raise HTTPException(status_code=400,detail="Academic year must be between 0001 and 9999.")
    report=service.report(db,term,academic_year,grade_level,stream,False)
    rows=[report["summary"]] if dataset=="summary" else report[dataset]
    if dataset=="learners":rows=[row for row in rows if service.matches_issue(row,issue)]
    metadata={"term":term,"academic_year":academic_year,"report_grade_filter":grade_level,
        "report_stream_filter":stream,"as_of":report["as_of"],"generated_at_utc":report["generated_at"],
        "population_basis":"current active enrollment","learner_issue_filter":issue if dataset=="learners" else "all"}
    flat=[{**metadata,**flatten(row)} for row in rows]
    # Empty exports retain filter metadata headings and contain no data rows.
    fields=list(flat[0]) if flat else list(metadata)+["no_matching_records"]
    buffer=io.StringIO(newline="")
    writer=csv.DictWriter(buffer,fieldnames=fields)
    writer.writeheader()
    for row in flat:writer.writerow({key:safe_cell(value) for key,value in row.items()})
    filename=f"school-report-{dataset}-{academic_year}-term-{term[-1]}.csv"
    return Response(content="\ufeff"+buffer.getvalue(),media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":f'attachment; filename="{filename}"',"Cache-Control":"no-store"})
