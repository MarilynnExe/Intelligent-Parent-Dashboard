"""
Parent Operations Router.

Exposes endpoints for:
    - Listing verified children linked to the logged-in parent
    - Querying assessments for a linked child
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_role
from app.models.academic import Assessment
from app.models.student import ParentStudent, Student
from app.models.user import User
from app.schemas.academic import AssessmentOut
from app.schemas.parent import ChildSummaryOut

router = APIRouter(
    prefix="/parent",
    tags=["Parent Operations"],
)


@router.get(
    "/my-children",
    response_model=List[ChildSummaryOut],
)
def get_my_children(
    current_user: User = Depends(require_role(["PARENT", "ADMIN"])),
    db: Session = Depends(get_db),
):
    """
    Retrieve list of learners linked to the logged-in parent via ParentStudent relationship.
    """
    results = (
        db.query(Student, ParentStudent.relationship_type)
        .join(ParentStudent, Student.student_id == ParentStudent.student_id)
        .filter(ParentStudent.parent_user_id == current_user.user_id)
        .order_by(Student.last_name, Student.first_name)
        .all()
    )

    children = []
    for student, rel in results:
        children.append(
            ChildSummaryOut(
                student_id=student.student_id,
                admission_number=student.admission_number,
                first_name=student.first_name,
                last_name=student.last_name,
                date_of_birth=student.date_of_birth,
                gender=student.gender,
                grade_level=student.grade_level,
                stream=student.stream,
                relationship_type=rel,
            )
        )

    return children


@router.get(
    "/children/{student_id}/assessments",
    response_model=List[AssessmentOut],
)
def get_child_assessments(
    student_id: int,
    current_user: User = Depends(require_role(["PARENT", "ADMIN"])),
    db: Session = Depends(get_db),
):
    """
    Retrieve assessment history for a parent's verified child.
    """
    if current_user.role == "PARENT":
        authorized = (
            db.query(ParentStudent)
            .filter(
                ParentStudent.parent_user_id == current_user.user_id,
                ParentStudent.student_id == student_id,
            )
            .first()
        )
        if not authorized:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to view this student's assessment records.",
            )

    return (
        db.query(Assessment)
        .filter(Assessment.student_id == student_id)
        .order_by(Assessment.assessment_date.desc())
        .all()
    )
