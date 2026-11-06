"""Backend-only generation input. The private RPC must return this same shape.

It holds private member data, so it must never be sent to the browser or logged.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.preferences import OptionalPreference


class GenerationMember(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    # An anonymous position such as "Member 1", never a name or account id.
    label: str = Field(pattern=r"^Member [0-9]+$")
    departure_city: str = Field(min_length=1, max_length=100)
    max_budget_sar: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    destinations: OptionalPreference = Field(default_factory=OptionalPreference)
    interests: OptionalPreference = Field(default_factory=OptionalPreference)
    flights: OptionalPreference = Field(default_factory=OptionalPreference)
    accommodation: OptionalPreference = Field(default_factory=OptionalPreference)

    @model_validator(mode="after")
    def places_and_flights_are_wishes(self):
        # Rihla combines everyone's places and flight wishes into one plan, so
        # they are always Flexible, even if older saves marked them Essential.
        for key in WISH_CATEGORIES:
            preference = getattr(self, key)
            if preference.importance != "Flexible":
                setattr(
                    self, key, preference.model_copy(update={"importance": "Flexible"})
                )
        return self


# Preferences the planner combines instead of enforcing one member's choice.
WISH_CATEGORIES = ("destinations", "flights")


class GenerationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trip_id: UUID
    shared_start: date
    shared_end: date
    members: list[GenerationMember] = Field(min_length=1)
    # The trip's length in days, chosen by the administrator inside the shared
    # dates. None lets the planner choose.
    trip_days: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def dates_in_order(self):
        if self.shared_start > self.shared_end:
            raise ValueError("Shared end must be on or after shared start.")
        if self.trip_days and self.trip_days > self.shared_days:
            raise ValueError("The trip is longer than the group's shared dates.")
        return self

    @property
    def shared_days(self) -> int:
        return (self.shared_end - self.shared_start).days + 1
