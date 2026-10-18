from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ChildSummaryOut(BaseModel):
    student_id: int
    admission_number: str
    first_name: str
    last_name: str
    date_of_birth: date
    gender: Optional[str] = None
    grade_level: str
    stream: Optional[str] = None
    relationship_type: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
