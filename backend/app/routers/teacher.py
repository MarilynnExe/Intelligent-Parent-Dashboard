from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_role

from app.models.user import User
from app.models.student import Student, TeacherAssignment

from app.schemas.teacher import (
    TeacherAssignmentOut,
    StudentSummaryOut
)

from app.models.academic import Assessment
from app.schemas.academic import (
    AssessmentCreate,
    AssessmentOut
)

from app.models.behaviour import Attendance
from app.schemas.attendance import (
    BulkAttendanceCreate,
    AttendanceOut
)

from app.models.behaviour import (
    BehaviourRecord,
    TeacherObservation
)

from app.schemas.behaviour import (
    BehaviourCreate,
    ObservationCreate
)

router = APIRouter(
    prefix="/teacher",
    tags=["Teacher Operations"]
)


def calculate_age(born: date) -> int:
    today = date.today()

    return (
        today.year
        - born.year
        - ((today.month, today.day) < (born.month, born.day))
    )


@router.get(
    "/assignments",
    response_model=List[TeacherAssignmentOut]
)
def get_teacher_assignments(
    current_user: User = Depends(
        require_role(["TEACHER"])
    ),
    db: Session = Depends(get_db)
):
    return (
        db.query(TeacherAssignment)
        .filter(
            TeacherAssignment.teacher_user_id
            == current_user.user_id
        )
        .all()
    )


@router.get(
    "/students",
    response_model=List[StudentSummaryOut]
)
def get_assigned_students(
    grade_level: str,
    stream: str,

    current_user: User = Depends(
        require_role(["TEACHER"])
    ),

    db: Session = Depends(get_db)
):
    # Check that this teacher actually teaches
    # this grade and stream.
    assignment = (
        db.query(TeacherAssignment)
        .filter(
            TeacherAssignment.teacher_user_id
            == current_user.user_id,

            TeacherAssignment.grade_level
            == grade_level,

            TeacherAssignment.stream
            == stream
        )
        .first()
    )

    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "You are not authorized to view "
                "students outside your assigned classes."
            )
        )

    students = (
        db.query(Student)
        .filter(
            Student.grade_level == grade_level,
            Student.stream == stream
        )
        .order_by(
            Student.last_name,
            Student.first_name
        )
        .all()
    )

    results = []

    for student in students:
        results.append(
            StudentSummaryOut(
                student_id=student.student_id,
                admission_number=student.admission_number,
                first_name=student.first_name,
                last_name=student.last_name,
                date_of_birth=student.date_of_birth,
                gender=student.gender,
                grade_level=student.grade_level,
                stream=student.stream
            )
        )

    return results

    @router.post(
    "/assessments",
    response_model=AssessmentOut
)
def record_assessment(
    data: AssessmentCreate,

    current_user: User = Depends(
        require_role(["TEACHER"])
    ),

    db: Session = Depends(get_db)
):
    student = (
        db.query(Student)
        .filter(
            Student.student_id == data.student_id
        )
        .first()
    )

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Student not found."
        )

    # IMPORTANT:
    # Verify teacher actually teaches this student's
    # grade/stream.
    authorized = (
        db.query(TeacherAssignment)
        .filter(
            TeacherAssignment.teacher_user_id
            == current_user.user_id,

            TeacherAssignment.grade_level
            == student.grade_level,

            TeacherAssignment.stream
            == student.stream,

            TeacherAssignment.subject_name
            == data.subject_name
        )
        .first()
    )

    if not authorized:
        raise HTTPException(
            status_code=403,
            detail=(
                "You are not authorized to record "
                "this student's assessment."
            )
        )

    if data.score > data.max_score:
        raise HTTPException(
            status_code=400,
            detail="Score cannot exceed maximum score."
        )

    percentage = round(
        (data.score / data.max_score) * 100,
        2
    )

    assessment = Assessment(
        student_id=data.student_id,
        subject_name=data.subject_name,
        academic_year=data.academic_year,
        term=data.term,
        assessment_type=data.assessment_type,
        score=data.score,
        max_score=data.max_score,
        percentage=percentage,
        assessment_date=(
            data.assessment_date
            or date.today()
        ),
        recorded_by_teacher_id=current_user.user_id
    )

    db.add(assessment)
    db.commit()
    db.refresh(assessment)

    return assessment

    @router.get(
    "/students/{student_id}/assessments",
    response_model=List[AssessmentOut]
)
def get_student_assessments(
    student_id: int,

    current_user: User = Depends(
        require_role(["TEACHER"])
    ),

    db: Session = Depends(get_db)
):
    student = (
        db.query(Student)
        .filter(Student.student_id == student_id)
        .first()
    )

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Student not found."
        )

    authorized = (
        db.query(TeacherAssignment)
        .filter(
            TeacherAssignment.teacher_user_id
            == current_user.user_id,

            TeacherAssignment.grade_level
            == student.grade_level,

            TeacherAssignment.stream
            == student.stream
        )
        .first()
    )

    if not authorized:
        raise HTTPException(
            status_code=403,
            detail="Unauthorized student access."
        )

    return (
        db.query(Assessment)
        .filter(
            Assessment.student_id == student_id
        )
        .order_by(
            Assessment.assessment_date.desc()
        )
        .all()
    )

    @router.post("/attendance/bulk")
def record_bulk_attendance(
    data: BulkAttendanceCreate,

    current_user: User = Depends(
        require_role(["TEACHER"])
    ),

    db: Session = Depends(get_db)
):
    updated = 0

    for item in data.entries:

        student = (
            db.query(Student)
            .filter(
                Student.student_id
                == item.student_id
            )
            .first()
        )

        if not student:
            continue

        # SECURITY CHECK
        authorized = (
            db.query(TeacherAssignment)
            .filter(
                TeacherAssignment.teacher_user_id
                == current_user.user_id,

                TeacherAssignment.grade_level
                == student.grade_level,

                TeacherAssignment.stream
                == student.stream
            )
            .first()
        )

        if not authorized:
            continue

        existing = (
            db.query(Attendance)
            .filter(
                Attendance.student_id
                == item.student_id,

                Attendance.record_date
                == data.record_date
            )
            .first()
        )

        if existing:
            existing.status = item.status
            existing.remarks = item.remarks
            existing.recorded_by_teacher_id = (
                current_user.user_id
            )
        else:
            attendance = Attendance(
                student_id=item.student_id,
                record_date=data.record_date,
                status=item.status,
                remarks=item.remarks,
                recorded_by_teacher_id=(
                    current_user.user_id
                )
            )

            db.add(attendance)

        updated += 1

    db.commit()

    return {
        "message": (
            f"Attendance updated for "
            f"{updated} learners."
        )
    }

    @router.post("/behaviour")
def record_behaviour(
    data: BehaviourCreate,

    current_user: User = Depends(
        require_role(["TEACHER"])
    ),

    db: Session = Depends(get_db)
):
    student = (
        db.query(Student)
        .filter(
            Student.student_id == data.student_id
        )
        .first()
    )

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Student not found."
        )

    authorized = (
        db.query(TeacherAssignment)
        .filter(
            TeacherAssignment.teacher_user_id
            == current_user.user_id,

            TeacherAssignment.grade_level
            == student.grade_level,

            TeacherAssignment.stream
            == student.stream
        )
        .first()
    )

    if not authorized:
        raise HTTPException(
            status_code=403,
            detail="Unauthorized student access."
        )

    record = BehaviourRecord(
        student_id=data.student_id,
        record_date=(
            data.record_date
            or date.today()
        ),
        category=data.category,
        rating=data.rating,
        teacher_note=data.teacher_note,
        recorded_by_teacher_id=current_user.user_id
    )

    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "message": "Behaviour record saved successfully.",
        "record_id": record.record_id
    }

    @router.post("/observations")
def add_teacher_observation(
    data: ObservationCreate,

    current_user: User = Depends(
        require_role(["TEACHER"])
    ),

    db: Session = Depends(get_db)
):
    student = (
        db.query(Student)
        .filter(
            Student.student_id == data.student_id
        )
        .first()
    )

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Student not found."
        )

    authorized = (
        db.query(TeacherAssignment)
        .filter(
            TeacherAssignment.teacher_user_id
            == current_user.user_id,

            TeacherAssignment.grade_level
            == student.grade_level,

            TeacherAssignment.stream
            == student.stream
        )
        .first()
    )

    if not authorized:
        raise HTTPException(
            status_code=403,
            detail="Unauthorized student access."
        )

    observation = TeacherObservation(
        student_id=data.student_id,
        observation_date=date.today(),
        term=data.term,
        academic_year=data.academic_year,
        observation_text=data.observation_text,
        teacher_id=current_user.user_id
    )

    db.add(observation)
    db.commit()
    db.refresh(observation)

    return {
        "message": "Teacher observation recorded successfully."
    }