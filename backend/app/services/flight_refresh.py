"""The light flight update: one ticket, checked again with Ignav.

Never uses Gemini or Tavily and never rebuilds a proposal. It changes only the
caller's own departure city's price, timestamp and availability.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from urllib.parse import quote

from app.core.config import Settings
from app.schemas.proposals import FlightLeg, Flights, Proposal, SarPrice
from app.services.flight_prices import (
    FlightQuery,
    IgnavError,
    IgnavProvider,
    airport_for_city,
    carrier_codes,
    flight_numbers,
    per_person,
    pick_link,
    usable_itineraries,
    without_tracking,
)
from app.services.flight_usage import FlightUsage
from app.services.proposal_generation import OptionRejected, budget_status
from app.services.trip_research import sar_amount

BookLeg = Literal["outbound", "inbound", "round_trip"]
Fallback = Literal["not_available", "limit", "demo"]


class NoRoute(Exception):
    """This member's departure city has no flights in the proposal."""


@dataclass
class LiveCheck:
    """The result of one check. `fallback` set means use the Google Flights link."""

    google_url: str
    fallback: Fallback | None = None
    itinerary: dict | None = None
    query: FlightQuery | None = None
    priced_at: datetime | None = None


def find_route(proposal: Proposal, city: str) -> Flights:
    wanted = city.strip().casefold()
    for route in proposal.flights:
        if route.origin.strip().casefold() == wanted:
            return route
    raise NoRoute


def route_airports(route: Flights) -> tuple[str | None, str | None]:
    """New proposals store airports. Older ones have them only in the fare's note."""
    origin = route.origin_airport or airport_for_city(route.origin)
    destination = route.destination_airport
    if destination is None:
        for item in route.price_per_person.evidence:
            found = re.search(r"\b([A-Z]{3})-([A-Z]{3})\b", item.quote)
            if found:
                origin, destination = origin or found.group(1), found.group(2)
                break
    return origin, destination


def google_flights_url(
    route: Flights, proposal: Proposal, leg: BookLeg, adults: int
) -> str:
    """A search link that never expires. Google may ignore the passenger count."""
    origin, destination = route_airports(route)
    start = origin or route.origin
    end = destination or proposal.cities[0].city
    outbound, back = proposal.start_date, proposal.end_date
    if route.legs:
        outbound = route.legs[0].date
        back = route.legs[-1].date
    if leg == "inbound":
        text = f"One way flights from {end} to {start} on {back}"
    elif leg == "outbound":
        text = f"One way flights from {start} to {end} on {outbound}"
    else:
        text = f"Flights from {start} to {end} on {outbound} through {back}"
    return "https://www.google.com/travel/flights?hl=en&curr=SAR&q=" + quote(
        f"{text} for {adults} adults"
    )


def _same_flight(part: dict | None, stored: FlightLeg) -> bool:
    if not part:
        return False
    if stored.flight_number:
        wanted = set(stored.flight_number.replace(" ", "").split(","))
        return wanted == {item.replace(" ", "") for item in flight_numbers(part)}
    carrier = stored.airline.value
    return bool(carrier) and str(part.get("carrier")).casefold() == carrier.casefold()


def matching_itinerary(body: dict, route: Flights, leg: BookLeg) -> dict | None:
    """The cheapest result holding the same flight, on the sides this action needs."""
    by_direction = {item.direction: item for item in route.legs}

    def fits(item: dict) -> bool:
        if leg != "inbound" and not _same_flight(
            item.get("outbound"), by_direction["outbound"]
        ):
            return False
        if leg != "outbound" and "return" in by_direction:
            return _same_flight(item.get("inbound"), by_direction["return"])
        return True

    found = [item for item in usable_itineraries(body) if fits(item)]
    return min(
        found, key=lambda item: Decimal(str(item["price"]["amount"])), default=None
    )


class FlightChecker:
    def __init__(
        self,
        settings: Settings,
        provider: IgnavProvider | None = None,
        usage: FlightUsage | None = None,
    ) -> None:
        self.settings = settings
        self.usage = usage or FlightUsage(settings.flight_usage_db)
        if provider is None and settings.ignav_api_key:
            provider = IgnavProvider(settings.ignav_api_key)
        self.provider = provider if settings.flight_price_provider == "ignav" else None
        self.cache_seconds = settings.flight_cache_minutes * 60

    def _can_spend(self, trip: str) -> bool:
        return (
            self.usage.spent_today(trip) < self.settings.trip_ignav_requests_per_day
            and self.usage.spent_today() < self.settings.daily_ignav_requests
        )

    async def _search(self, query: FlightQuery, trip: str) -> tuple[float, dict] | None:
        """Cached fares, or a new search. None means a limit stopped the search."""
        key = f"search|{query}"
        cached = self.usage.cache_get(key, self.cache_seconds)
        if cached:
            self.usage.record("search", trip, True)
            return cached
        if not self._can_spend(trip):
            return None
        body = await self.provider.search(query)
        self.usage.record("search", trip, False)
        self.usage.cache_put(key, body)
        return datetime.now(UTC).timestamp(), body

    async def links(self, check: LiveCheck, trip: str) -> dict | None:
        ignav_id = str(check.itinerary["ignav_id"])
        key = f"links|{check.query}|{ignav_id}"
        cached = self.usage.cache_get(key, self.cache_seconds)
        if cached:
            self.usage.record("booking_links", trip, True)
            return cached[1]
        if not self._can_spend(trip):
            return None
        body = await self.provider.booking_links(ignav_id)
        self.usage.record("booking_links", trip, False)
        self.usage.cache_put(key, body)
        return body

    async def check(
        self,
        proposal: Proposal,
        route: Flights,
        leg: BookLeg,
        adults: int,
        trip: str,
        member: str,
    ) -> LiveCheck:
        check = LiveCheck(google_flights_url(route, proposal, leg, adults))
        if self.settings.proposals_demo_mode:
            check.fallback = "demo"
            return check
        if not self.usage.take_member_action(
            member, self.settings.member_flight_actions_per_hour
        ):
            check.fallback = "limit"
            return check
        origin, destination = route_airports(route)
        if self.provider is None or not origin or not destination:
            check.fallback = "not_available"
            return check
        check.query = FlightQuery(
            origin,
            destination,
            route.legs[0].date,
            # A one_way route still searches the trip's real return day.
            route.legs[-1].date if len(route.legs) > 1 else proposal.end_date,
            max(adults, 1),
        )
        try:
            found = await self._search(check.query, trip)
        except IgnavError:
            check.fallback = "not_available"
            return check
        if found is None:
            check.fallback = "limit"
            return check
        check.priced_at = datetime.fromtimestamp(found[0], UTC)
        check.itinerary = matching_itinerary(found[1], route, leg)
        if check.itinerary is None:
            check.fallback = "not_available"
        return check


@dataclass
class BookResult:
    url: str
    fallback: Fallback | None = None
    seller: str | None = None
    exact_flight: bool = False
    price_sar: Decimal | None = None
    previous_price_sar: Decimal | None = None


async def book_flight(
    checker: FlightChecker,
    proposal: Proposal,
    city: str,
    leg: BookLeg,
    adults: int,
    trip: str,
    member: str,
) -> BookResult:
    route = find_route(proposal, city)
    check = await checker.check(proposal, route, leg, adults, trip, member)
    if check.fallback:
        return BookResult(check.google_url, check.fallback)
    try:
        links = await checker.links(check, trip)
    except IgnavError:
        return BookResult(check.google_url, "not_available")
    if links is None:
        return BookResult(check.google_url, "limit")
    directions = {"outbound", "inbound"} if leg == "round_trip" else {leg}
    parts = [check.itinerary[name] for name in directions if check.itinerary.get(name)]
    # Checked against this flight's airline, route and dates before it is returned.
    link = pick_link(
        links.get("booking_options") or [],
        directions,
        check.query,
        carrier_codes(*parts),
    )
    if link is None:
        return BookResult(check.google_url, "not_available")
    if leg == "round_trip":
        offer = check.itinerary["price"]
        previous = route.price_per_person.amount_sar
    else:
        offer = link.get("price") or {}
        direction = "outbound" if leg == "outbound" else "return"
        stored = next(item for item in route.legs if item.direction == direction)
        previous = stored.price.amount_sar
    price = per_person(
        sar_amount(
            str(offer.get("amount", "")), str(offer.get("currency", "")).upper()
        ),
        check.query.adults,
        checker.settings.ignav_price_scope == "total",
    )
    return BookResult(
        without_tracking(str(link["url"])),
        seller=str(link.get("provider_name") or "") or None,
        exact_flight=link.get("specificity") == "exact_flight",
        price_sar=price,
        previous_price_sar=(
            previous if price and previous and abs(price - previous) >= 1 else None
        ),
    )


@dataclass
class RefreshResult:
    url: str
    flights: Flights | None = None
    budget_status: str | None = None
    fallback: Fallback | None = None
    updated: bool = False


def _new_price(old: SarPrice, amount: Decimal | None, verified: bool) -> SarPrice:
    if amount is None:
        return old
    status = "Sourced" if verified else "Estimated"
    if not old.evidence:
        status = "Unconfirmed"
    return SarPrice(amount_sar=amount, status=status, evidence=old.evidence)


async def refresh_flights(
    checker: FlightChecker,
    proposal: Proposal,
    city: str,
    adults: int,
    ceiling: Decimal,
    trip: str,
    member: str,
) -> RefreshResult:
    route = find_route(proposal, city)
    both = "round_trip"
    check = await checker.check(proposal, route, both, adults, trip, member)
    if check.fallback == "not_available" and check.query and check.itinerary is None:
        # The same flight is gone: say so on the saved route, and keep the old price.
        if check.priced_at:
            gone = route.model_copy(update={"group_availability": "not_found"})
            return RefreshResult(check.google_url, gone, None, "not_available", True)
    if check.fallback:
        return RefreshResult(check.google_url, fallback=check.fallback)
    total_only = checker.settings.ignav_price_scope == "total"
    price = check.itinerary["price"]
    amount = per_person(
        sar_amount(str(price["amount"]), str(price["currency"]).upper()),
        check.query.adults,
        total_only,
    )
    legs = list(route.legs)
    if route.trip_type != "round_trip":
        # Separate bookings have their own prices, which need the links request.
        try:
            links = await checker.links(check, trip)
        except IgnavError:
            links = None
        for option in (links or {}).get("booking_options") or []:
            names = set(option.get("legs") or [])
            direction = {"outbound": "outbound", "inbound": "return"}.get(
                next(iter(names)) if len(names) == 1 else ""
            )
            offer = next(
                (
                    item["price"]
                    for item in option.get("links") or []
                    if item.get("price")
                ),
                None,
            )
            if direction is None or offer is None:
                continue
            legs = [
                item.model_copy(
                    update={
                        "price": _new_price(
                            item.price,
                            per_person(
                                sar_amount(
                                    str(offer["amount"]), str(offer["currency"]).upper()
                                ),
                                check.query.adults,
                                total_only,
                            ),
                            False,
                        )
                    }
                )
                if item.direction == direction
                else item
                for item in legs
            ]
    verified = (
        route.trip_type == "round_trip"
        and price.get("status") == "verified"
        and str(price["currency"]).upper() == "SAR"
    )
    fresh = Flights.model_validate(
        route.model_copy(
            update={
                "legs": legs,
                "price_per_person": _new_price(
                    route.price_per_person, amount, verified
                ),
                "priced_at": check.priced_at,
                "group_availability": "available",
            }
        ).model_dump()
    )
    flights = [
        fresh if item.origin == route.origin else item for item in proposal.flights
    ]
    try:
        status = budget_status(
            proposal.cities, flights, proposal.intercity_transport, ceiling
        )
    except OptionRejected:
        status = "over_group_budget"
    return RefreshResult(check.google_url, fresh, status, None, True)


__all__ = [
    "BookResult",
    "FlightChecker",
    "NoRoute",
    "RefreshResult",
    "book_flight",
    "refresh_flights",
]
