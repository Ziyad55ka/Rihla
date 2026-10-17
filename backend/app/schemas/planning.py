from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Readiness = Literal["Ready", "Incomplete"]
MissingField = Literal[
    "departure_city", "max_budget_sar", "available_start", "available_end"
]


class OwnReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Readiness
    missing_fields: list[MissingField]

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


class PlanningStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    own_readiness: OwnReadiness
    member_readiness: list[MemberReadiness] | None
    shared_dates: SharedDates
