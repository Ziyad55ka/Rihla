import re
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class OptionalPreference(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    value: str = Field(default="", max_length=500)
    importance: Literal["Essential", "Flexible"] = "Flexible"


class MemberPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    departure_city: str = Field(default="", max_length=100)
    max_budget_sar: Decimal | None = Field(
        default=None, gt=0, max_digits=12, decimal_places=2
    )
    available_start: date | None = None
    available_end: date | None = None
    destinations: OptionalPreference = Field(default_factory=OptionalPreference)
    interests: OptionalPreference = Field(default_factory=OptionalPreference)
    flights: OptionalPreference = Field(default_factory=OptionalPreference)
    accommodation: OptionalPreference = Field(default_factory=OptionalPreference)

    @field_validator("available_start", "available_end", mode="before")
    @classmethod
    def calendar_date_only(cls, value):
        if value is not None and (
            not isinstance(value, str)
            or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None
        ):
            raise ValueError("Use a calendar date in YYYY-MM-DD format.")
        return value

    @model_validator(mode="after")
    def dates_in_order(self):
        if (
            self.available_start is not None
            and self.available_end is not None
            and self.available_start > self.available_end
        ):
            raise ValueError("End date must be on or after start date.")
        return self


class SavedPreferences(MemberPreferences):
    currency: Literal["SAR"] = "SAR"
    updated_at: datetime | None = None
