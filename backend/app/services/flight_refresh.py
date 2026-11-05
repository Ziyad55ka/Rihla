"""The light flight update: one ticket, checked again with every source switched on.

Never uses Gemini or Tavily and never rebuilds a proposal. It changes only the caller's
own departure city's flights, and always asks the sources directly, with no local cache.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from urllib.parse import quote

from app.core.config import Settings
from app.schemas.proposals import (
    Evidence,
    FlightLeg,
    Flights,
    InfoField,
    Proposal,
    SarPrice,
)
from app.services.flight_prices import (
    FlightFare,
    FlightQuery,
    IgnavError,
    airport_for_city,
    clearly_better,
    fare_from_itinerary,
    fare_quote,
    flight_numbers,
    format_duration,
    per_person,
    steady_itinerary,
    usable_itineraries,
)
from app.services.flight_usage import FlightUsage
from app.services.price_accuracy import PriceAccuracy
from app.services.proposal_generation import OptionRejected, _fare_leg, budget_status
from app.services.travel_providers import FlightProvider, live_flight_providers
from app.services.trip_research import sar_amount

logger = logging.getLogger(__name__)

BookLeg = Literal["outbound", "inbound", "round_trip"]
# not_available: no source has this flight or a replacement. check_failed: no source
# answered, so nothing is known. no_link: it exists, with no page that can open it.
Fallback = Literal["not_available", "limit", "demo", "check_failed", "no_link"]
# agent: the same flight, cheaper through a travel agent than the airline.
AlternativeReason = Literal["gone", "no_link", "cheaper", "agent"]


class NoRoute(Exception):
    """This member's departure city has no flights in the proposal."""


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
    """The last resort. Google may ignore the airline or the passenger count."""
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
    wanted = "return" if leg == "inbound" else "outbound"
    airline = next(
        (item.airline.value for item in route.legs if item.direction == wanted), None
    )
    if airline and airline.isascii():
        text += f" on {airline}"
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


def matching_itinerary(body: dict, route: Flights) -> dict | None:
    """The cheapest result holding this same trip."""
    by_direction = {item.direction: item for item in route.legs}

    def fits(item: dict) -> bool:
        if not _same_flight(item.get("outbound"), by_direction["outbound"]):
            return False
        if "return" in by_direction:
            return _same_flight(item.get("inbound"), by_direction["return"])
        return True

    found = [item for item in usable_itineraries(body) if fits(item)]
    return min(
        found, key=lambda item: Decimal(str(item["price"]["amount"])), default=None
    )


def _name(provider: FlightProvider) -> str:
    return getattr(provider, "name", "ignav")


@dataclass
class Asked:
    """One source's answer to one search."""

    provider: FlightProvider
    body: dict
    # When the source says it fetched this, which may be before this request.
    at: datetime


@dataclass
class Quote:
    asked: Asked
    itinerary: dict
    # None when no page can open this flight.
    fare: FlightFare | None


def _observed(body: dict) -> datetime:
    try:
        return datetime.fromisoformat(
            str(body.get("observed_at")).replace("Z", "+00:00")
        )
    except ValueError:
        return datetime.now(UTC)


class FlightChecker:
    def __init__(
        self,
        settings: Settings,
        provider: FlightProvider | None = None,
        usage: FlightUsage | None = None,
        providers: list[FlightProvider] | None = None,
    ) -> None:
        self.settings = settings
        self.usage = usage or FlightUsage(settings.flight_usage_db)
        if providers is not None:
            self.providers = providers
        elif provider is not None:
            self.providers = [provider]
        else:
            self.providers = live_flight_providers(settings)
        self.total_only = settings.ignav_price_scope == "total"
        self.accuracy = PriceAccuracy(
            settings.price_accuracy_db, settings.price_gap_log_percent
        )

    def can_spend(self, provider: FlightProvider, trip: str) -> bool:
        name = _name(provider)
        return (
            self.usage.spent_today(trip, name) < self.settings.trip_requests_per_day
            and self.usage.spent_today(None, name)
            < self.settings.daily_requests_per_source
        )

    async def search(
        self, provider: FlightProvider, query: FlightQuery, trip: str
    ) -> Asked | None:
        """A new search. None means this source's limit stopped it."""
        if not self.can_spend(provider, trip):
            return None
        body = await provider.search(query)
        self.usage.record("search", trip, False, _name(provider))
        return Asked(provider, body, _observed(body))

    async def ask_all(
        self, query: FlightQuery, trip: str
    ) -> tuple[list[Asked], bool, bool]:
        """Every source at once. Returns answers, and whether a limit or failure hit."""

        async def one(provider: FlightProvider) -> Asked | IgnavError | None:
            try:
                return await self.search(provider, query, trip)
            except IgnavError as error:
                logger.info("flight_source_failed source=%s", _name(provider))
                return error

        answers = await asyncio.gather(*(one(item) for item in self.providers))
        return (
            [item for item in answers if isinstance(item, Asked)],
            any(item is None for item in answers),
            any(isinstance(item, IgnavError) for item in answers),
        )

    async def quote(
        self, asked: Asked, itinerary: dict, query: FlightQuery, trip: str
    ) -> Quote:
        if not self.can_spend(asked.provider, trip):
            return Quote(asked, itinerary, None)
        try:
            links = await asked.provider.booking_links(str(itinerary["ignav_id"]))
            self.usage.record("booking_links", trip, False, _name(asked.provider))
            fare = fare_from_itinerary(itinerary, links, query, self.total_only)
        except IgnavError:
            return Quote(asked, itinerary, None)
        self.accuracy.record(
            fare.airline,
            f"{query.origin_airport}-{query.destination_airport}",
            fare.accuracy_gap(),
        )
        return Quote(asked, itinerary, replace(fare, provider=_name(asked.provider)))


def best_quote(quotes: list[Quote], conflict_percent: Decimal) -> Quote:
    """The airline's own price, then a link to the flight itself, then the newest.

    When sources disagree by more than the limit, the closest to the airline wins.
    """

    def rank(item: Quote) -> tuple:
        fare = item.fare
        return (
            fare is None,
            not (fare and fare.seller_type == "airline"),
            not (fare and fare.exact),
            -item.asked.at.timestamp(),
        )

    ordered = sorted(quotes, key=rank)
    priced = [item for item in ordered if item.fare]
    if len(priced) < 2:
        return ordered[0]
    amounts = [Decimal(item.fare.amount) for item in priced]
    if max(amounts) <= min(amounts) * (1 + conflict_percent / 100):
        return ordered[0]
    logger.info(
        "flight_price_conflict sources=%s percent=%s",
        ",".join(_name(item.asked.provider) for item in priced),
        round((max(amounts) / min(amounts) - 1) * 100),
    )
    official = [item for item in priced if item.fare.seller_type == "airline"]
    if not official:
        return ordered[0]
    target = Decimal(official[0].fare.amount)
    return min(priced, key=lambda item: abs(Decimal(item.fare.amount) - target))


def route_from_fare(
    route: Flights, fare: FlightFare, query: FlightQuery, at: datetime
) -> Flights:
    # The new fare's note, under the source already cited for this route.
    cited = route.price_per_person.evidence
    evidence = (
        [Evidence(source_id=cited[0].source_id, quote=fare_quote(fare, query)[:500])]
        if cited
        else []
    )
    if not evidence:
        status = "Unconfirmed"
    elif fare.verified and fare.trip_type == "round_trip" and fare.currency == "SAR":
        status = "Sourced"
    else:
        status = "Estimated"
    named = "Sourced" if evidence else "Unconfirmed"
    return Flights(
        origin=route.origin,
        trip_type=fare.trip_type,
        legs=[_fare_leg(item, evidence) for item in fare.legs],
        airline=InfoField(value=fare.airline, status=named, evidence=evidence),
        duration=InfoField(
            value=format_duration(fare.duration_minutes),
            status=named,
            evidence=evidence,
        ),
        price_per_person=SarPrice(
            amount_sar=sar_amount(fare.amount, fare.currency),
            status=status,
            evidence=evidence,
        ),
        priced_at=at,
        origin_airport=query.origin_airport,
        destination_airport=query.destination_airport,
        group_availability="available",
        fare_basis=route.fare_basis if route.fare_basis == "solo" else "group",
        solo_saving_sar=route.solo_saving_sar if route.fare_basis == "solo" else None,
        provider=fare.provider,
        seller_type=fare.seller_type,
        price_source=fare.price_source,
        cabin_class=fare.cabin_class,
        fare_name=fare.fare_name,
        checked_bags=fare.checked_bags,
        carry_on_bags=fare.carry_on_bags,
    )


@dataclass
class Alternative:
    reason: AlternativeReason
    flights: Flights
    url: str | None
    seller: str | None
    exact_flight: bool
    provider: str
    price_sar: Decimal | None
    within_budget: bool | None


def _status(
    proposal: Proposal, route: Flights, fresh: Flights, ceiling: Decimal | None
) -> str | None:
    if ceiling is None:
        return None
    flights = [
        fresh if item.origin == route.origin else item for item in proposal.flights
    ]
    try:
        return budget_status(
            proposal.cities, flights, proposal.intercity_transport, ceiling
        )
    except OptionRejected:
        return "over_group_budget"


def _carriers(itinerary: dict) -> frozenset[str]:
    return frozenset(
        str((itinerary.get(name) or {}).get("carrier"))
        for name in ("outbound", "inbound")
        if itinerary.get(name)
    )


def _minutes(itinerary: dict) -> int:
    return sum(
        int((itinerary.get(name) or {}).get("duration_minutes") or 0)
        for name in ("outbound", "inbound")
    )


async def find_alternative(
    checker: FlightChecker,
    asked_list: list[Asked],
    proposal: Proposal,
    route: Flights,
    query: FlightQuery,
    trip: str,
    ceiling: Decimal | None,
    reason: AlternativeReason,
    avoid: frozenset[str] = frozenset(),
) -> Alternative | None:
    """The best other flight on the same dates, with a price its seller agrees with.

    The same preference as generation: one airline unless another trip is clearly
    better. At most two link requests, because each one is a billed request.
    """
    settings = checker.settings
    tried = 0
    for asked in asked_list:
        options = [
            item
            for item in usable_itineraries(asked.body)
            if not (avoid and _carriers(item) == avoid)
        ]
        if not options:
            continue
        # A trip over twice as long as the shortest is not a reasonable replacement.
        shortest = min(_minutes(item) for item in options)
        options = [item for item in options if _minutes(item) <= shortest * 2]
        steady = steady_itinerary({"itineraries": options})
        cheapest = min(options, key=lambda item: Decimal(str(item["price"]["amount"])))
        better = (
            steady is not None
            and cheapest is not steady
            and clearly_better(
                cheapest,
                steady,
                settings.split_min_saving_percent / 100,
                settings.split_max_extra_duration_percent / 100,
            )
        )
        order = [cheapest, steady] if better else [steady or cheapest, cheapest]
        seen: set[frozenset[str]] = set()
        for itinerary in order:
            if tried >= 2 or _carriers(itinerary) in seen:
                continue
            seen.add(_carriers(itinerary))
            tried += 1
            fare = (await checker.quote(asked, itinerary, query, trip)).fare
            if (
                fare is None
                or any(item.booking_url is None for item in fare.legs)
                or fare.price_gap_percent() > settings.price_conflict_percent
            ):
                continue
            fresh = route_from_fare(route, fare, query, asked.at).model_copy(
                update={"fare_basis": "group", "solo_saving_sar": None}
            )
            status = _status(proposal, route, fresh, ceiling)
            return Alternative(
                reason,
                fresh,
                fare.legs[0].booking_url,
                fare.provider_name,
                fare.exact,
                _name(asked.provider),
                fresh.price_per_person.amount_sar,
                None if status is None else status != "over_group_budget",
            )
    return None


@dataclass
class CheckResult:
    url: str | None
    fallback: Fallback | None = None
    seller: str | None = None
    seller_type: str | None = None
    provider: str | None = None
    exact_flight: bool = False
    price_sar: Decimal | None = None
    # Set only when the price differs from the one saved.
    previous_price_sar: Decimal | None = None
    # What to save for this city, when `updated`.
    flights: Flights | None = None
    budget_status: str | None = None
    updated: bool = False
    alternative: Alternative | None = None
    checked_at: datetime | None = None


def _agent_option(
    fare: FlightFare,
    fresh: Flights,
    proposal: Proposal,
    route: Flights,
    ceiling: Decimal | None,
    settings: Settings,
) -> Alternative | None:
    """An agent clearly cheaper than the airline, for the same flight."""
    shown = fresh.price_per_person.amount_sar
    amount = sar_amount(fare.agent_amount, fare.currency)
    if not fare.agent_url or not amount or not shown:
        return None
    if amount > shown * (1 - settings.agent_cheaper_percent / 100):
        return None
    option = fresh.model_copy(
        update={
            "price_per_person": fresh.price_per_person.model_copy(
                update={"amount_sar": amount}
            ),
            "seller_type": "third_party",
        }
    )
    status = _status(proposal, route, option, ceiling)
    return Alternative(
        "agent",
        option,
        fare.agent_url,
        fare.agent_name,
        False,
        fare.provider,
        amount,
        None if status is None else status != "over_group_budget",
    )


def _changed(price: Decimal | None, previous: Decimal | None) -> Decimal | None:
    return previous if price and previous and abs(price - previous) >= 1 else None


def _leg_of(route: Flights | FlightFare, leg: BookLeg):
    wanted = "return" if leg == "inbound" else "outbound"
    return next((item for item in route.legs if item.direction == wanted), None)


async def _with_alone_saving(
    checker: FlightChecker,
    quote: Quote,
    route: Flights,
    query: FlightQuery,
    trip: str,
    fresh: Flights,
) -> Flights:
    """For a party: is the same flight cheaper one person at a time? One more search."""
    if query.adults <= 1:
        return fresh
    try:
        alone = await checker.search(
            quote.asked.provider, replace(query, adults=1), trip
        )
    except IgnavError:
        return fresh
    match = matching_itinerary(alone.body, route) if alone else None
    shown = fresh.price_per_person
    if match is None or shown.amount_sar is None:
        return fresh
    together = per_person(
        sar_amount(str(quote.itinerary["price"]["amount"]), "SAR"),
        query.adults,
        checker.total_only,
    )
    solo = sar_amount(str(match["price"]["amount"]), "SAR")
    if not together or not solo or together - solo < 1:
        return fresh
    # Compared at the search's price, and taken off the seller's.
    saving = together - solo
    return fresh.model_copy(
        update={
            "fare_basis": "solo",
            "solo_saving_sar": saving,
            "price_per_person": shown.model_copy(
                update={"amount_sar": shown.amount_sar - saving}
            ),
        }
    )


async def check_flight(
    checker: FlightChecker,
    proposal: Proposal,
    city: str,
    leg: BookLeg,
    adults: int,
    trip: str,
    member: str,
    ceiling: Decimal | None = None,
    refreshing: bool = False,
) -> CheckResult:
    route = find_route(proposal, city)
    # A price for one person booking alone is checked as that same booking.
    party = max(1 if route.fare_basis == "solo" and not refreshing else adults, 1)
    google = google_flights_url(route, proposal, leg, party)
    settings = checker.settings
    if settings.proposals_demo_mode:
        return CheckResult(google, "demo")
    if not checker.usage.take_member_action(
        member, settings.member_flight_actions_per_hour
    ):
        return CheckResult(google, "limit")
    origin, destination = route_airports(route)
    if not checker.providers or not origin or not destination:
        return CheckResult(google, "check_failed")
    query = FlightQuery(
        origin,
        destination,
        route.legs[0].date,
        # A one_way route still searches the trip's real return day.
        route.legs[-1].date if len(route.legs) > 1 else proposal.end_date,
        party,
        route.return_airport,
    )
    asked_list, limited, failed = await checker.ask_all(query, trip)
    if not asked_list:
        return CheckResult(
            google, "limit" if limited and not failed else "check_failed"
        )
    now = datetime.now(UTC)
    matches = [
        (asked, match)
        for asked in asked_list
        if (match := matching_itinerary(asked.body, route))
    ]

    async def alternative_for(
        reason: AlternativeReason, avoid: frozenset[str] = frozenset()
    ) -> Alternative | None:
        return await find_alternative(
            checker, asked_list, proposal, route, query, trip, ceiling, reason, avoid
        )

    if not matches:
        found = await alternative_for("gone")
        if found is None:
            gone = route.model_copy(update={"group_availability": "not_found"})
            return CheckResult(
                google, "not_available", flights=gone, updated=True, checked_at=now
            )
        return CheckResult(
            found.url,
            seller=found.seller,
            seller_type=found.flights.seller_type,
            provider=found.provider,
            exact_flight=found.exact_flight,
            price_sar=found.price_sar,
            previous_price_sar=_changed(
                found.price_sar, route.price_per_person.amount_sar
            ),
            flights=found.flights,
            budget_status=_status(proposal, route, found.flights, ceiling),
            updated=True,
            alternative=found,
            checked_at=now,
        )
    quotes = await asyncio.gather(
        *(checker.quote(asked, match, query, trip) for asked, match in matches)
    )
    best = best_quote(list(quotes), settings.price_conflict_percent)
    fare = best.fare
    if fare is None:
        # It exists, but no page opens it: keep it, update the price, offer another.
        price = best.itinerary["price"]
        amount = per_person(
            sar_amount(str(price["amount"]), str(price["currency"]).upper()),
            party,
            checker.total_only,
        )
        fresh = route.model_copy(
            update={
                "price_per_person": route.price_per_person.model_copy(
                    update={"amount_sar": amount or route.price_per_person.amount_sar}
                ),
                "priced_at": best.asked.at,
                "group_availability": "available",
            }
        )
        return CheckResult(
            google,
            "no_link",
            provider=_name(best.asked.provider),
            price_sar=amount,
            previous_price_sar=_changed(amount, route.price_per_person.amount_sar),
            flights=fresh,
            budget_status=_status(proposal, route, fresh, ceiling),
            updated=True,
            alternative=await alternative_for("no_link", _carriers(best.itinerary)),
            checked_at=now,
        )
    fresh = route_from_fare(route, fare, query, best.asked.at)
    if refreshing:
        fresh = await _with_alone_saving(checker, best, route, query, trip, fresh)
    if leg == "round_trip":
        price_now = fresh.price_per_person.amount_sar
        previous = route.price_per_person.amount_sar
        url = _leg_of(fare, leg).booking_url if fare.trip_type == "round_trip" else None
    else:
        price_now = _leg_of(fresh, leg).price.amount_sar
        previous = _leg_of(route, leg).price.amount_sar
        url = _leg_of(fare, leg).booking_url
    seller = _leg_of(fare, leg).seller or fare.provider_name
    missing = (
        any(item.booking_url is None for item in fare.legs) if refreshing else not url
    )
    alternative = None
    agent = _agent_option(fare, fresh, proposal, route, ceiling, settings)
    if missing:
        alternative = await alternative_for("no_link", _carriers(best.itinerary))
    elif agent:
        # The same flight needs no other search, so this costs no request.
        alternative = agent
    elif fare.price_gap_percent() > settings.price_conflict_percent:
        # The seller asks far above what the search showed, as Gulf Air did.
        cheaper = await alternative_for("cheaper", _carriers(best.itinerary))
        shown = fresh.price_per_person.amount_sar
        if cheaper and cheaper.price_sar and shown and cheaper.price_sar < shown:
            alternative = cheaper
    return CheckResult(
        url or google,
        "no_link" if missing else None,
        seller=seller,
        seller_type=fare.seller_type,
        provider=_name(best.asked.provider),
        exact_flight=fare.exact and bool(url),
        price_sar=price_now,
        previous_price_sar=_changed(price_now, previous),
        flights=fresh,
        budget_status=_status(proposal, route, fresh, ceiling),
        updated=True,
        alternative=alternative,
        checked_at=now,
    )


async def book_flight(
    checker: FlightChecker,
    proposal: Proposal,
    city: str,
    leg: BookLeg,
    adults: int,
    trip: str,
    member: str,
    ceiling: Decimal | None = None,
) -> CheckResult:
    return await check_flight(
        checker, proposal, city, leg, adults, trip, member, ceiling
    )


async def refresh_flights(
    checker: FlightChecker,
    proposal: Proposal,
    city: str,
    adults: int,
    ceiling: Decimal,
    trip: str,
    member: str,
) -> CheckResult:
    return await check_flight(
        checker,
        proposal,
        city,
        "round_trip",
        adults,
        trip,
        member,
        ceiling,
        refreshing=True,
    )


__all__ = [
    "CheckResult",
    "FlightChecker",
    "NoRoute",
    "book_flight",
    "check_flight",
    "refresh_flights",
]
