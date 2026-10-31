from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.preferences import MemberPreferences

Readiness = Literal["Ready", "Incomplete"]
MissingField = Literal[
    "departure_city", "max_budget_sar", "available_start", "available_end"
]


class OwnReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Readiness
    missing_fields: list[MissingField]
    has_saved_preferences: bool = Field(strict=True)

    @model_validator(mode="after")
    def status_matches_missing_fields(self):
        if (self.status == "Ready") != (len(self.missing_fields) == 0):
            raise ValueError("Readiness must match the missing fields.")
        return self


class MemberReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    status: Readiness


class SharedDates(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["pending", "conflict", "available"]
    start: date | None
    end: date | None
    duration_days: int | None = Field(ge=1)

    @model_validator(mode="after")
    def consistent_result(self):
        if self.status == "available":
            if (
                self.start is None
                or self.end is None
                or self.start > self.end
                or self.duration_days != (self.end - self.start).days + 1
            ):
                raise ValueError("Invalid shared date result.")
        elif any(
            value is not None for value in (self.start, self.end, self.duration_days)
        ):
            raise ValueError("Unresolved dates must not expose a partial interval.")
        return self


class MemberDates(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    available_start: date | None
    available_end: date | None

    @model_validator(mode="after")
    def dates_in_order(self):
        if (
            self.available_start is not None
            and self.available_end is not None
            and self.available_start > self.available_end
        ):
            raise ValueError("Invalid member date range.")
        return self


class PlanningStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    all_members_ready: bool = Field(strict=True)
    own_readiness: OwnReadiness
    member_readiness: list[MemberReadiness] | None
    member_dates: list[MemberDates]
    shared_dates: SharedDates


ConflictCategory = Literal[
    "readiness", "dates", "destinations", "flights", "accommodation", "budget"
]


class GroupConflicts(BaseModel):
    """Shown to every member. Categories only, like the group date conflict."""

    model_config = ConfigDict(extra="forbid")
    conflicts: list[ConflictCategory]
    # This member has an Essential in these categories and should review it.
    own_review: list[ConflictCategory]
    can_generate: bool = Field(strict=True)

    @model_validator(mode="after")
    def blocked_while_conflicted(self):
        if self.can_generate == bool(self.conflicts):
            raise ValueError("Generation is allowed only with no conflicts.")
        return self


class DateCheckInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    available_start: date
    available_end: date

    @field_validator("available_start", "available_end", mode="before")
    @classmethod
    def calendar_date_only(cls, value):
        return MemberPreferences.calendar_date_only(value)

    @model_validator(mode="after")
    def dates_in_order(self):
        if self.available_start > self.available_end:
            raise ValueError("End date must be on or after start date.")
        return self


class DateCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["pending", "conflict", "available"]
