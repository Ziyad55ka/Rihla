from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Account(BaseModel):
    id: UUID
    email: str


class ProfileInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    display_name: str = Field(min_length=2, max_length=80)


class Profile(ProfileInput):
    id: UUID
    created_at: datetime
