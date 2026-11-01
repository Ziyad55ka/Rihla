"""The proposal JSON shared with US-11 to US-15.

Other copy: frontend/src/types/proposal.ts. Any change must be made in both files.
Team guide: docs/proposal-schema-handoff.md.
Sample data: docs/examples/proposals.mock.json.
"""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# How far a value can be trusted.
# Allowed: Sourced, Estimated, Unconfirmed, Not available.
# Sourced: a source states it. Needs evidence. Example: "Saudia".
# Estimated: approximate or converted. Needs evidence. Example: "about 5 hours".
# Unconfirmed: unclear or general knowledge. Evidence may be empty.
# Not available: unknown. The value is null and evidence is empty.
InfoStatus = Literal["Sourced", "Estimated", "Unconfirmed", "Not available"]
# Same values as InfoStatus.
# Only a live flight fare can be Sourced: other web prices are never offers.
PriceStatus = Literal["Sourced", "Estimated", "Unconfirmed", "Not available"]
# The preference a Flexible adjustment relates to.
# Allowed: destinations, interests, flights, accommodation.
PreferenceCategory = Literal["destinations", "interests", "flights", "accommodation"]
# Says only whether the group fits, never the budget behind that answer.
# within_group_budget: the total fits and every price has evidence.
# includes_unconfirmed: the known total fits, but a price is uncertain or missing.
# over_group_budget: the total does not fit. Such a proposal is rejected, not returned.
BudgetStatus = Literal[
    "within_group_budget", "includes_unconfirmed", "over_group_budget"
]

# Proposals are shared with the whole trip, so explanations must stay general.
# Rejects digits, the word member, and SAR, in English and Arabic.
PRIVATE_DETAIL = re.compile(r"\d|\b(members?|sar)\b|عضو|أعضاء|ريال", re.IGNORECASE)


# How the flights are booked. Allowed values:
# round_trip: one booking for both directions.
# split: two separate bookings. The total is an estimate.
# one_way: outbound only. The return cost is not counted.
TripType = Literal["round_trip", "split", "one_way"]
# A separate booking link, or null when there is none.
# Example: "https://www.booking.com/searchresults.html?ss=Cairo".
BookingUrl = Annotated[str, Field(pattern=r"^https://", max_length=2000)] | None


# Base for every model: unknown fields are rejected, and text is trimmed.
class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# The proof behind a value: which source said it, in its own words.
class Evidence(StrictModel):
    # The id of an entry in Proposal.sources. Example: 2.
    source_id: int = Field(ge=1)
    # A short quote from that source. Example: "The flight takes about 5 hours."
    quote: str = Field(min_length=1, max_length=500)


# A text value with its trust level.
class InfoField(StrictModel):
    # The text to show, or null when Not available. Example: "Saudia".
    value: str | None
    # See InfoStatus. Example: "Sourced".
    status: InfoStatus
    # Required for Sourced and Estimated. May be empty for Unconfirmed.
    evidence: list[Evidence]

    @model_validator(mode="after")
    def status_matches_value(self):
        if self.status == "Not available":
            if self.value is not None or self.evidence:
                raise ValueError("Not available must have no value or evidence.")
        elif not self.value:
            raise ValueError("A shown status needs a value.")
        elif self.status != "Unconfirmed" and not self.evidence:
            raise ValueError("A Sourced or Estimated value needs evidence.")
        return self


# A price in Saudi riyals with its trust level.
class SarPrice(StrictModel):
    # Above zero, two decimals at most, or null. JSON sends a string.
    # Example: "1200.00".
    amount_sar: Decimal | None = Field(gt=0, max_digits=12, decimal_places=2)
    # See PriceStatus. Example: "Estimated".
    status: PriceStatus
    # Required for Sourced and Estimated. May be empty for Unconfirmed.
    evidence: list[Evidence]

    @model_validator(mode="after")
    def status_matches_amount(self):
        if self.status == "Not available":
            if self.amount_sar is not None or self.evidence:
                raise ValueError("Not available must have no amount or evidence.")
        elif self.amount_sar is None:
            raise ValueError("A shown status needs an amount.")
        elif self.status != "Unconfirmed" and not self.evidence:
            raise ValueError("A Sourced or Estimated price needs evidence.")
        return self


def _not_sourced(price: SarPrice) -> SarPrice:
    if price.status == "Sourced":
        raise ValueError("Only a live flight fare can be Sourced.")
    return price


# A web page or booking link cited by Evidence.
class ProposalSource(StrictModel):
    # Unique within the proposal. Example: 1.
    id: int = Field(ge=1)
    # The page title. Example: "Istanbul hotel guide".
    title: str = Field(min_length=1, max_length=300)
    # The page address. Example: "https://example.com/istanbul".
    url: str = Field(pattern=r"^https?://", max_length=2000)
    # booking: an approved booking site. ideas: gives ideas only. flight: a fare note,
    # never listed to users. Set when reading. Older data has none.
    kind: Literal["booking", "ideas", "flight"] | None = None


# One direction of a flight trip.
class FlightLeg(StrictModel):
    # Allowed: outbound, return.
    direction: Literal["outbound", "return"]
    # The travel date. JSON sends YYYY-MM-DD. Example: "2026-12-13".
    date: date
    # The airline for this direction. Example value: "Saudia".
    airline: InfoField
    # The flight time for this direction. Example value: "3h 20m".
    duration: InfoField
    # On a round_trip, set only when the seller states each direction's price itself.
    # It is never worked out by dividing the total.
    price: SarPrice
    # A link saved at generation. It can expire, so the page asks for a fresh one.
    booking_url: BookingUrl
    # Null on older proposals. Example: "SV 1020". Connections: "SV 1020, SV 45".
    flight_number: str | None = None
    # Local airport time, or null on older proposals. Example: "2026-12-13T08:30".
    departure_time: str | None = None
    # Local airport time, or null on older proposals.
    arrival_time: str | None = None
    # 0 is nonstop. Null on older proposals.
    stops: int | None = Field(default=None, ge=0)
    # Where those stops are, or empty on older proposals. Example: ["ATH"].
    stop_airports: list[str] = []
    # Who sells this leg, or null. It can differ from the airline. Example: "Saudia".
    seller: str | None = None


# General facts about an airline's cheapest fare, never a promise for a ticket.
class AirlineFareNote(StrictModel):
    # Two characters. Example: "GF".
    code: str
    name_en: str
    name_ar: str
    # The fare's name. Example: "Economy Light".
    fare_en: str
    fare_ar: str
    # The usual checked bag: 0 is none, and null is not confirmed.
    checked_kg: int | None = Field(default=None, ge=0)


# The flights from one departure city.
class Flights(StrictModel):
    # Stored per departure city. rihla_get_proposals returns only the caller's.
    # Example: "Riyadh".
    origin: str = Field(min_length=1, max_length=100)
    # round_trip: one booking. split: two bookings. one_way: return not included.
    trip_type: TripType
    # One leg for one_way. Otherwise outbound then return.
    legs: list[FlightLeg] = Field(min_length=1, max_length=2)
    # The outbound airline, as a summary. Example value: "Saudia".
    airline: InfoField
    # The outbound flight time, as a summary. Example value: "3h 20m".
    duration: InfoField
    # The whole trip's cost. On one_way, the return is not counted.
    # Sourced only for a verified round_trip fare in SAR.
    price_per_person: SarPrice
    # When this price was checked, or null on older proposals.
    priced_at: datetime | None = None
    # Three-letter codes, or null on older proposals. Example: "RUH".
    origin_airport: str | None = None
    destination_airport: str | None = None
    # available: the search for everyone from this city found this flight.
    # not_found: it found none, so they may need different flights.
    # unknown: not checked. Never holds a seat count or a traveller count.
    group_availability: Literal["available", "not_found", "unknown"] = "unknown"
    # group: priced as one booking for everyone from this city. solo: each person
    # booking alone was cheaper, so price_per_person is that price. Null when older.
    fare_basis: Literal["group", "solo"] | None = None
    # With solo: how much less per person than one booking together.
    solo_saving_sar: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    # Which source gave this price. Example: "ignav". Null on older proposals.
    provider: str | None = None
    # airline: sold by the airline itself. third_party: an agent. Null when unknown.
    seller_type: str | None = None
    # seller: the seller's own price. search: the search result's. Null when older.
    price_source: Literal["seller", "search"] | None = None
    # Null when the source does not say. Examples: "economy" and "Main Cabin".
    cabin_class: str | None = None
    fare_name: str | None = None
    # Allowance per person, or null when the source does not say.
    checked_bags: int | None = Field(default=None, ge=0)
    carry_on_bags: int | None = Field(default=None, ge=0)
    # Added on reading, never saved: what is generally known of these airlines' fares.
    airline_fares: list[AirlineFareNote] = []

    @model_validator(mode="after")
    def legs_match_trip_type(self):
        directions = [leg.direction for leg in self.legs]
        if self.trip_type == "one_way":
            if directions != ["outbound"]:
                raise ValueError("A one_way trip has only an outbound leg.")
        elif directions != ["outbound", "return"]:
            raise ValueError("This trip needs an outbound and a return leg.")
        if self.trip_type == "round_trip":
            if self.legs[0].booking_url != self.legs[1].booking_url:
                raise ValueError("A round_trip has one booking link.")
        elif self.price_per_person.status == "Sourced":
            raise ValueError("Only a round_trip fare can be Sourced.")
        return self


# A free photo with its credit. Added on reading, never saved.
class PlaceImage(StrictModel):
    # The picture itself. Example: "https://upload.wikimedia.org/x.jpg".
    url: str = Field(pattern=r"^https://", max_length=2000)
    # The picture's page, with its full licence.
    source_url: str = Field(pattern=r"^https://", max_length=2000)
    # Who made it, as plain text, or null. Example: "A. Photographer".
    artist: str | None = Field(default=None, max_length=200)
    # Example: "CC BY-SA 4.0".
    license: str = Field(min_length=1, max_length=100)


# A stay in one city.
class CityStay(StrictModel):
    # The position in the route, counting up from 1. Example: 1.
    order: int = Field(ge=1)
    # The city name. Example: "Cairo".
    city: str = Field(min_length=1, max_length=100)
    # The city in Arabic, or null on older proposals.
    city_ar: str | None = Field(default=None, min_length=1, max_length=100)
    # Nights here. All stays must add up to the trip dates. Example: 4.
    nights: int = Field(ge=0)
    # A suggested hotel. Example value: "Mock Hotel".
    hotel_name: InfoField
    # The price per night. It cannot be Sourced. Example amount: "450.00".
    hotel_price_per_night: SarPrice
    # A Booking.com search, or null. It does not confirm availability or price.
    booking_url: BookingUrl
    # A suggested area from idea sources, or null. Example: "Le Marais".
    area: str | None = Field(default=None, max_length=150)
    # When this price was checked, or null on older proposals.
    priced_at: datetime | None = None
    # A page for this hotel itself, as its source gave it, or null. Example: Trip.com.
    hotel_url: BookingUrl = None
    # Who gave the hotel and price when it was a live source. Example: "Trip.com".
    hotel_source: str | None = Field(default=None, max_length=50)
    # A photo of this city, or null.
    image: PlaceImage | None = None

    @field_validator("hotel_price_per_night")
    @classmethod
    def hotel_price_is_not_sourced(cls, price: SarPrice) -> SarPrice:
        return _not_sourced(price)


# Travel between two consecutive cities.
class IntercityTransfer(StrictModel):
    # The city left. Example: "Cairo".
    from_city: str = Field(min_length=1, max_length=100)
    # The city reached. Example: "Alexandria".
    to_city: str = Field(min_length=1, max_length=100)
    # How to travel. Example value: "Train".
    mode: InfoField
    # The travel time. Example value: "1.5 hours".
    duration: InfoField
    # The price for one person. It cannot be Sourced. Example amount: "53.00".
    price_per_person: SarPrice
    # Station names, or null. Nothing fills these yet. Example: "Paris Gare de l'Est".
    from_station: str | None = Field(default=None, max_length=100)
    to_station: str | None = Field(default=None, max_length=100)

    @field_validator("price_per_person")
    @classmethod
    def transfer_price_is_not_sourced(cls, price: SarPrice) -> SarPrice:
        return _not_sourced(price)


# Explains a Flexible preference that this proposal could not meet.
class FlexibleAdjustment(StrictModel):
    # See PreferenceCategory. Example: "accommodation".
    category: PreferenceCategory
    # General text with no digits or member details.
    # Example: "A standard option is suggested."
    explanation: str = Field(min_length=1, max_length=300)

    @field_validator("explanation")
    @classmethod
    def no_private_detail(cls, value: str) -> str:
        if PRIVATE_DETAIL.search(value):
            raise ValueError("Explanations must not mention budgets or members.")
        return value


# One complete trip option.
class Proposal(StrictModel):
    # This proposal's own id, a UUID.
    id: UUID
    # The trip it belongs to, a UUID.
    trip_id: UUID
    # The generation round. It goes up each time proposals are regenerated. Example: 1.
    version: int = Field(ge=1)
    # Allowed: 1, 2, 3.
    option_number: int = Field(ge=1, le=3)
    # A general title with no private details. Example: "Nile Heritage Experience".
    title: str = Field(min_length=1, max_length=150)
    # The title in Arabic, or null on older proposals. The page then shows `title`.
    title_ar: str | None = Field(default=None, min_length=1, max_length=150)
    # The title in English, or null on older proposals. The page then shows `title`.
    title_en: str | None = Field(default=None, min_length=1, max_length=150)
    # The place shown to users. Example: "Cairo".
    destination: str = Field(min_length=1, max_length=100)
    # The place in Arabic, or null on older proposals.
    destination_ar: str | None = Field(default=None, min_length=1, max_length=100)
    # The first day. JSON sends YYYY-MM-DD. Example: "2026-12-13".
    start_date: date
    # The last day. JSON sends YYYY-MM-DD. Example: "2026-12-17".
    end_date: date
    # At least one stay, in route order.
    cities: list[CityStay] = Field(min_length=1)
    # A member receives only their own city, so this list can be empty.
    flights: list[Flights]
    # One entry between each pair of consecutive cities. Empty for a single city.
    intercity_transport: list[IntercityTransfer]
    # Empty when every Flexible preference was met.
    flexible_adjustments: list[FlexibleAdjustment]
    # See BudgetStatus. Example: "includes_unconfirmed".
    budget_status: BudgetStatus
    # Every source cited by Evidence in this proposal.
    sources: list[ProposalSource]
    # A photo of the destination, or null.
    image: PlaceImage | None = None

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
    def one_way_cost_is_not_settled(self):
        one_way = any(route.trip_type == "one_way" for route in self.flights)
        if one_way and self.budget_status == "within_group_budget":
            raise ValueError("A one_way trip leaves its return cost uncounted.")
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

    def without_uncited_sources(self) -> "Proposal":
        cited = {
            item.source_id
            for field in self.evidence_fields()
            for item in field.evidence
        }
        return self.model_copy(
            update={"sources": [item for item in self.sources if item.id in cited]}
        )

    # A new field with evidence must be added here, or its sources get dropped.
    def evidence_fields(self) -> list[InfoField | SarPrice]:
        fields: list[InfoField | SarPrice] = []
        for route in self.flights:
            fields += [route.airline, route.duration, route.price_per_person]
            for leg in route.legs:
                fields += [leg.airline, leg.duration, leg.price]
        for stay in self.cities:
            fields += [stay.hotel_name, stay.hotel_price_per_night]
        for leg in self.intercity_transport:
            fields += [leg.mode, leg.duration, leg.price_per_person]
        return fields


# Exactly three different proposals. Used for the mock and demo files.
class ProposalSet(StrictModel):
    # Options 1, 2 and 3, which must differ in destination or cities.
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
