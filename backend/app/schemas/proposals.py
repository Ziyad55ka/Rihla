"""The proposal JSON shared with US-11 to US-15. Mirrored in frontend/src/types."""

import re
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

InfoStatus = Literal["Sourced", "Estimated", "Unconfirmed", "Not available"]
# Public web prices are never booking offers, so a price cannot be Sourced.
PriceStatus = Literal["Estimated", "Unconfirmed", "Not available"]
PreferenceCategory = Literal["destinations", "interests", "flights", "accommodation"]

# Proposals are shared with the whole trip, so explanations must stay general.
PRIVATE_DETAIL = re.compile(
    r"\d|\b(budget|member|sar)\b|ميزاني|عضو|ريال", re.IGNORECASE
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Evidence(StrictModel):
    source_id: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=500)


class InfoField(StrictModel):
    value: str | None
    status: InfoStatus
    evidence: list[Evidence]

    @model_validator(mode="after")
    def status_matches_value(self):
        if self.status == "Not available":
            if self.value is not None or self.evidence:
                raise ValueError("Not available must have no value or evidence.")
        elif not self.value or not self.evidence:
            raise ValueError("A shown value needs evidence.")
        return self


class SarPrice(StrictModel):
    amount_sar: Decimal | None = Field(gt=0, max_digits=12, decimal_places=2)
    status: PriceStatus
    evidence: list[Evidence]

    @model_validator(mode="after")
    def status_matches_amount(self):
        if self.status == "Not available":
            if self.amount_sar is not None or self.evidence:
                raise ValueError("Not available must have no amount or evidence.")
        elif self.amount_sar is None or not self.evidence:
            raise ValueError("A shown price needs evidence.")
        return self


class ProposalSource(StrictModel):
    id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=300)
    url: str = Field(pattern=r"^https?://", max_length=2000)


class Flights(StrictModel):
    # Stored per departure city. Browser responses pass through view_for_member.
    origin: str = Field(min_length=1, max_length=100)
    airline: InfoField
    duration: InfoField
    price_per_person: SarPrice


class CityStay(StrictModel):
    order: int = Field(ge=1)
    city: str = Field(min_length=1, max_length=100)
    nights: int = Field(ge=0)
    hotel_name: InfoField
    hotel_price_per_night: SarPrice


class IntercityTransfer(StrictModel):
    from_city: str = Field(min_length=1, max_length=100)
    to_city: str = Field(min_length=1, max_length=100)
    mode: InfoField
    duration: InfoField
    price_per_person: SarPrice


class FlexibleAdjustment(StrictModel):
    category: PreferenceCategory
    explanation: str = Field(min_length=1, max_length=300)

    @field_validator("explanation")
    @classmethod
    def no_private_detail(cls, value: str) -> str:
        if PRIVATE_DETAIL.search(value):
            raise ValueError("Explanations must not mention budgets or members.")
        return value


class Proposal(StrictModel):
    id: UUID
    trip_id: UUID
    version: int = Field(ge=1)
    option_number: int = Field(ge=1, le=3)
    title: str = Field(min_length=1, max_length=150)
    destination: str = Field(min_length=1, max_length=100)
    start_date: date
    end_date: date
    cities: list[CityStay] = Field(min_length=1)
    flights: list[Flights]
    intercity_transport: list[IntercityTransfer]
    flexible_adjustments: list[FlexibleAdjustment]
    sources: list[ProposalSource]

    @model_validator(mode="after")
    def consistent_itinerary(self):
        if self.start_date > self.end_date:
            raise ValueError("End date must be on or after start date.")
        names = [stay.city for stay in sorted(self.cities, key=lambda s: s.order)]
        if [stay.order for stay in self.cities] != list(range(1, len(self.cities) + 1)):
            raise ValueError("City order must count up from 1.")
        if (
            sum(stay.nights for stay in self.cities)
            != (self.end_date - self.start_date).days
        ):
            raise ValueError("City nights must add up to the trip dates.")
        legs = [(leg.from_city, leg.to_city) for leg in self.intercity_transport]
        if legs != list(zip(names, names[1:], strict=False)):
            raise ValueError("Transfers must connect the cities in order.")
        return self

    @model_validator(mode="after")
    def evidence_uses_listed_sources(self):
        known = {source.id for source in self.sources}
        if len(known) != len(self.sources):
            raise ValueError("Source ids must be unique.")
        origins = [route.origin.strip().casefold() for route in self.flights]
        if len(set(origins)) != len(origins):
            raise ValueError("Each departure city can appear once.")
        for field in self.evidence_fields():
            if any(item.source_id not in known for item in field.evidence):
                raise ValueError("Evidence must cite a listed source.")
        return self

    def evidence_fields(self) -> list[InfoField | SarPrice]:
        fields: list[InfoField | SarPrice] = []
        for route in self.flights:
            fields += [route.airline, route.duration, route.price_per_person]
        for stay in self.cities:
            fields += [stay.hotel_name, stay.hotel_price_per_night]
        for leg in self.intercity_transport:
            fields += [leg.mode, leg.duration, leg.price_per_person]
        return fields


class ProposalSet(StrictModel):
    proposals: list[Proposal] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def distinct_options(self):
        if sorted(item.option_number for item in self.proposals) != [1, 2, 3]:
            raise ValueError("Proposals must be options 1, 2 and 3.")
        routes = {
            (item.destination, tuple(stay.city for stay in item.cities))
            for item in self.proposals
        }
        if len(routes) != 3:
            raise ValueError("Proposals must differ in destination or cities.")
        return self
