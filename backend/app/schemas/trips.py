from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

TripRole = Literal["administrator", "member"]


class CreateTrip(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    title: str = Field(min_length=2, max_length=100)
    description: str = Field(default="", max_length=500)


class JoinTrip(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(pattern=r"^(?:[0-9a-f]{64}|[0-9]{6})$")


class TripSummary(BaseModel):
    id: UUID
    title: str
    description: str
    created_at: datetime
    role: TripRole
    member_count: int = Field(ge=1)


class TripMember(BaseModel):
    user_id: UUID
    display_name: str
    role: TripRole
    joined_at: datetime


class TripDetail(TripSummary):
    members: list[TripMember]


class JoinResult(BaseModel):
    trip: TripDetail
    already_member: bool


class InvitationStatus(BaseModel):
    exists: bool
    expires_at: datetime | None
    revoked: bool


class InvitationCreated(BaseModel):
    token: str = Field(pattern=r"^[0-9a-f]{64}$")
    code: str = Field(pattern=r"^[0-9]{6}$")
    expires_at: datetime
