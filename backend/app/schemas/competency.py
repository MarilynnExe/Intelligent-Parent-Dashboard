from datetime import date
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Level = Literal["BELOW_EXPECTATIONS", "APPROACHING_EXPECTATIONS", "MEETING_EXPECTATIONS", "EXCEEDING_EXPECTATIONS"]

class CompetencyDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Text = Field(max_length=150)
    strand: str = Field(default="", max_length=150)
    description: str = Field(default="", max_length=4000)

class CompetencyCreate(CompetencyDetails):
    grade_level: Text = Field(max_length=50)
    stream: Text = Field(max_length=50)
    subject_name: Text = Field(max_length=100)

class CompetencyStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_archived: bool

class ObservationDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    term: Literal["Term 1", "Term 2", "Term 3"]
    academic_year: str = Field(pattern=r"^[1-9][0-9]{3}$")
    observed_on: date
    level: Level
    evidence: Text = Field(max_length=2000)

class ObservationCreate(ObservationDetails):
    student_id: int = Field(gt=0)
