from typing import Annotated
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

class StartConversation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_id: int = Field(gt=0)
    contact_user_id: int = Field(gt=0)

class SendMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    client_message_id: UUID

class ReadMessages(BaseModel):
    model_config = ConfigDict(extra="forbid")
    through_message_id: int = Field(gt=0)
