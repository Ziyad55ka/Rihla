"""Swappable flight fare sources. Returning None means use the web search instead."""

import hashlib
import logging
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Protocol
from urllib.parse import unquote, urlsplit

import httpx2 as httpx

from app.core.config import Settings
from app.services.flight_usage import FlightUsage
from app.services.price_accuracy import PriceAccuracy

logger = logging.getLogger(__name__)

IGNAV_BASE_URL = "https://ignav.com/api"
MAX_BOOKING_URL_LENGTH = 2000
CITY_AIRPORTS = {
    "riyadh": "RUH",
    "الرياض": "RUH",
    "jeddah": "JED",
    "jedda": "JED",
    "جدة": "JED",
    "dammam": "DMM",
    "الدمام": "DMM",
    "khobar": "DMM",
    "الخبر": "DMM",
    "medina": "MED",
    "madinah": "MED",
    "المدينة": "MED",
    "المدينة المنورة": "MED",
    "abha": "AHB",
    "أبها": "AHB",
    "tabuk": "TUU",
    "تبوك": "TUU",
    "taif": "TIF",
    "الطائف": "TIF",
    "qassim": "ELQ",
    "القصيم": "ELQ",
    "jazan": "GIZ",
    "جازان": "GIZ",
    "hail": "HAS",
    "حائل": "HAS",
}


def airport_for_city(city: str) -> str | None:
    return CITY_AIRPORTS.get(" ".join(city.casefold().split()))


@dataclass(frozen=True)
class FlightQuery:
    origin_airport: str
    destination_airport: str
    departure_date: date
    return_date: date
    # Everyone flying from this city, so results have seats for all of them.
    adults: int = 1
    # Open-jaw: the return flight leaves from here instead of the destination,
    # for a trip that ends in another city (Paris, then Barcelona home).
    return_from_airport: str | None = None

    @property
    def open_jaw(self) -> bool:
        return bool(
            self.return_from_airport
            and self.return_from_airport != self.destination_airport
        )

    @property
    def return_origin(self) -> str:
        return self.return_from_airport if self.open_jaw else self.destination_airport  # type: ignore[return-value]


@dataclass(frozen=True)
class FareLeg:
    direction: Literal["outbound", "return"]
    date: str
    airline: str | None
    duration_minutes: int | None
    # A link's own price, which covers only this leg. None on a round_trip.
    amount: str | None
    currency: str | None
    booking_url: str | None
    flight_number: str | None = None
    departure_time: str | None = None
    arrival_time: str | None = None
    stops: int | None = None
    seller: str | None = None
    stop_airports: tuple[str, ...] = ()


@dataclass(frozen=True)
class FlightFare:
    airline: str
    duration_minutes: int
    amount: str
    currency: str
    # True only for a checked price whose link books both directions together.
    verified: bool
    provider_name: str
    trip_type: Literal["round_trip", "split", "one_way"]
    legs: tuple[FareLeg, ...]
    # Per person, set when booking alone beats booking together. `amount` is then alone.
    solo_saving: str | None = None
    # What the search showed for one person, before the seller's own price.
    search_amount: str | None = None
    # seller: the link's own price. search: the search's, with no price on a link.
    price_source: Literal["seller", "search"] = "search"
    # The link opens this flight, rather than a list to choose from.
    exact: bool = False
    seller_type: str | None = None
    fare_name: str | None = None
    cabin_class: str | None = None
    checked_bags: int | None = None
    carry_on_bags: int | None = None
    provider: str = "ignav"
    # When the source fetched this fare, in ISO form, or null when unknown.
    observed_at: str | None = None
    # The cheapest agent for the whole trip, when the seller chosen is the airline.
    agent_name: str | None = None
    agent_url: str | None = None
    agent_amount: str | None = None
    # Google Flights also lists these exact flights, both ways, on these dates.
    schedule_confirmed: bool = False

    def accuracy_gap(self) -> Decimal | None:
        """The gap to record: None when no seller stated a price to compare."""
        return self.price_gap_percent() if self.price_source == "seller" else None

    def price_gap_percent(self) -> Decimal:
        """How far the seller's price is above what the search showed."""
        if not self.search_amount or self.price_source != "seller":
            return Decimal(0)
        shown = Decimal(self.search_amount)
        return (Decimal(self.amount) / shown - 1) * 100 if shown > 0 else Decimal(0)

    @property
    def source_url(self) -> str:
        for leg in self.legs:
            if leg.booking_url:
                return leg.booking_url
        return "https://ignav.com/"


class FlightPriceProvider(Protocol):
    requests_made: int

    async def find(self, query: FlightQuery) -> FlightFare | None: ...


class WebSearchOnly:
    """Always falls through to the Tavily search and Gemini extraction."""

    requests_made = 0

    async def find(self, query: FlightQuery) -> FlightFare | None:
        return None


class FareCache(Protocol):
    def get(self, key: str) -> list[dict] | None: ...

    def put(self, key: str, results: list[dict]) -> None: ...


class IgnavError(Exception):
    """Holds only a status or short code, never a response body or the key."""


class IgnavProvider:
    name = "ignav"

    def __init__(
        self,
        api_key: str,
        cache: FareCache | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        *,
        price_is_total: bool = False,
        split_min_saving_percent: Decimal = Decimal(15),
        split_max_extra_duration_percent: Decimal = Decimal(30),
        on_request: Callable[[str], None] | None = None,
        on_fare: Callable[[FlightFare, FlightQuery], None] | None = None,
        price_conflict_percent: Decimal = Decimal(10),
        cache_seconds: float = 900,
        verifier: Any = None,
    ) -> None:
        # A second source (GoogleFlightsCheck) every kept flight must also be on.
        self.verifier = verifier
        self.price_conflict_percent = price_conflict_percent
        self.on_fare = on_fare
        self.cache_seconds = cache_seconds
        self.api_key = api_key
        self.cache = cache
        self.transport = transport
        self.requests_made = 0
        self.price_is_total = price_is_total
        self.split_saving = split_min_saving_percent / 100
        self.split_extra = split_max_extra_duration_percent / 100
        self.on_request = on_request
        # Searches that returned no trip, so the party may not fit on one flight.
        self.no_itinerary: set[FlightQuery] = set()

    async def _post(self, path: str, body: dict) -> dict:
        self.requests_made += 1
        if self.on_request:
            self.on_request(path.rsplit("/", 1)[-1])
        try:
            async with httpx.AsyncClient(
                timeout=45.0,
                trust_env=False,
                transport=self.transport,
                headers={"X-Api-Key": self.api_key},
            ) as client:
                response = await client.post(f"{IGNAV_BASE_URL}{path}", json=body)
        except httpx.RequestError as error:
            raise IgnavError("unreachable") from error
        if response.status_code != 200:
            raise IgnavError(f"http_{response.status_code}")
        try:
            return response.json()
        except ValueError as error:
            raise IgnavError("invalid_json") from error

    async def search(self, query: FlightQuery) -> dict:
        """One search request. Prices come back in SAR through the SA market."""
        if query.open_jaw:
            # Flexible search with two legs; read back in the round-trip shape.
            body = await self._post(
                "/fares/search",
                {
                    "legs": [
                        {
                            "origin": query.origin_airport,
                            "destination": query.destination_airport,
                            "departure_date": query.departure_date.isoformat(),
                        },
                        {
                            "origin": query.return_origin,
                            "destination": query.origin_airport,
                            "departure_date": query.return_date.isoformat(),
                        },
                    ],
                    "adults": query.adults,
                    "market": "SA",
                },
            )
            return as_round_trip(body)
        return await self._post(
            "/fares/round-trip",
            {
                "origin": query.origin_airport,
                "destination": query.destination_airport,
                "departure_date": query.departure_date.isoformat(),
                "return_date": query.return_date.isoformat(),
                "adults": query.adults,
                "market": "SA",
            },
        )

    async def booking_links(self, ignav_id: str) -> dict:
        return named_legs(
            await self._post("/fares/booking-links", {"ignav_id": ignav_id})
        )

    async def _fare(self, choice: dict, query: FlightQuery) -> FlightFare | None:
        links = await self.booking_links(str(choice["ignav_id"]))
        try:
            fare = fare_from_itinerary(choice, links, query, self.price_is_total)
            if self.on_fare:
                self.on_fare(fare, query)
            return fare
        except IgnavError as error:
            if str(error) != "no_booking_link":
                raise
            return None

    async def _best_fare(self, body: dict, query: FlightQuery) -> FlightFare | None:
        """Prefer one airline both ways, unless another trip is clearly better.

        At most two links requests, because each one is a billed request.
        """
        cheapest = cheapest_itinerary(body)
        steady = steady_itinerary(body) or cheapest
        fare = await self._fare(steady, query)
        worth_it = cheapest is not steady and clearly_better(
            cheapest, steady, self.split_saving, self.split_extra
        )
        if fare is not None and fare.price_gap_percent() > self.price_conflict_percent:
            # The seller asks far more than the search showed, so try another airline.
            other = other_airline_itinerary(body, steady)
            second = await self._fare(other, query) if other else None
            if second and Decimal(second.amount) < Decimal(fare.amount):
                return second
            return fare
        if fare is not None and not worth_it:
            return fare
        if cheapest is steady:
            return fare
        return await self._fare(cheapest, query) or fare

    async def _cheaper_alone(self, fare: FlightFare, query: FlightQuery) -> FlightFare:
        """Compare the same flight booked together and alone. One more request."""
        if query.adults <= 1:
            return fare
        wanted = {leg.direction: leg.flight_number for leg in fare.legs}
        if not all(wanted.values()):
            return fare
        try:
            body = await self.search(replace(query, adults=1))
        except IgnavError:
            return fare
        same = [
            item
            for item in usable_itineraries(body)
            if ", ".join(flight_numbers(item["outbound"])) == wanted["outbound"]
            and (
                "return" not in wanted
                or ", ".join(flight_numbers(item.get("inbound") or {}))
                == wanted["return"]
            )
        ]
        alone = min(same, key=_amount, default=None)
        if alone is None or str(alone["price"]["currency"]).upper() != fare.currency:
            return fare
        # Compared at the search's price, and taken off the seller's.
        saving = Decimal(fare.search_amount or fare.amount) - _amount(alone)
        if saving < 1:
            return fare
        return replace(
            fare,
            amount=str(Decimal(fare.amount) - saving),
            verified=fare.verified and alone["price"].get("status") == "verified",
            solo_saving=str(saving),
        )

    async def _keep_listed(self, body: dict, query: FlightQuery) -> dict | None:
        """Only trips whose outbound Google Flights also sells; None if none is."""
        listed = await self.verifier.listed_outbound(query)
        if listed is None:
            return body
        from app.services.google_flights_check import flight_key

        kept = [
            item
            for item in body.get("itineraries") or []
            if flight_key(flight_numbers(item.get("outbound") or {})) in listed
        ]
        if not usable_itineraries({"itineraries": kept}):
            logger.info("flight_not_listed source=google_flights direction=outbound")
            return None
        return {**body, "itineraries": kept}

    async def _confirmed(
        self, body: dict, query: FlightQuery
    ) -> tuple[FlightFare | None, bool]:
        """The best fare whose return Google Flights also sells. Up to three tries."""
        from app.services.google_flights_check import flight_key

        for _ in range(3):
            fare = await self._best_fare(body, query)
            if fare is None:
                return None, False
            numbers = {
                leg.direction: flight_key(leg.flight_number) for leg in fare.legs
            }
            verdict = await self.verifier.confirm(
                query, numbers.get("outbound", ()), numbers.get("return", ())
            )
            if verdict is not False:
                return fare, verdict is True
            logger.info("flight_not_listed source=google_flights direction=return")
            body = {
                **body,
                "itineraries": [
                    item
                    for item in body.get("itineraries") or []
                    if (
                        flight_key(flight_numbers(item.get("outbound") or {})),
                        flight_key(flight_numbers(item.get("inbound") or {})),
                    )
                    != (numbers.get("outbound", ()), numbers.get("return", ()))
                ],
            }
            if cheapest_itinerary(body) is None:
                return None, False
        return None, False

    async def find(self, query: FlightQuery) -> FlightFare | None:
        checked = "checked|" if self.verifier else ""
        key = hashlib.sha256(f"ignav-legs|{checked}{query}".encode()).hexdigest()
        cached = self.cache.get(key) if self.cache else None
        if cached and time.time() - cached[0].get("cached_at", 0) < self.cache_seconds:
            saved = dict(cached[0])
            saved.pop("cached_at")
            saved["legs"] = tuple(
                FareLeg(**{**leg, "stop_airports": tuple(leg.get("stop_airports", ()))})
                for leg in saved["legs"]
            )
            return FlightFare(**saved)
        try:
            body = await self.search(query)
            observed = body.get("observed_at")
            if cheapest_itinerary(body) is None:
                logger.info("flight_provider_fallback reason=no_itinerary")
                self.no_itinerary.add(query)
                return None
            confirmed = False
            if self.verifier is not None:
                listed = await self._keep_listed(body, query)
                if listed is None:
                    return None
                fare, confirmed = await self._confirmed(listed, query)
            else:
                fare = await self._best_fare(body, query)
            if fare is None:
                logger.info("flight_provider_fallback reason=no_booking_link")
                return None
            fare = await self._cheaper_alone(fare, query)
            fare = replace(
                fare,
                observed_at=str(observed) if observed else None,
                schedule_confirmed=confirmed,
            )
        except IgnavError as error:
            logger.info("flight_provider_fallback reason=%s", error)
            return None
        except (KeyError, TypeError, ValueError, AttributeError):
            logger.info("flight_provider_fallback reason=unexpected_response")
            return None
        if self.cache:
            self.cache.put(key, [{**asdict(fare), "cached_at": time.time()}])
        return fare


def as_round_trip(body: dict) -> dict:
    """A flexible search's two legs, named outbound and inbound like a round trip."""
    for item in body.get("itineraries") or []:
        legs = item.get("legs")
        if isinstance(legs, list) and len(legs) == 2 and "outbound" not in item:
            item["outbound"], item["inbound"] = legs[0], legs[1]
    return body


def named_legs(links: dict) -> dict:
    """Booking options from a flexible search use leg_indexes; name them."""
    names = {0: "outbound", 1: "inbound"}
    for option in links.get("booking_options") or []:
        indexes = option.get("leg_indexes")
        if "legs" not in option and isinstance(indexes, list):
            option["legs"] = [names[i] for i in indexes if i in names]
    return links


def _amount(itinerary: dict) -> Decimal:
    try:
        return Decimal(str(itinerary["price"]["amount"]))
    except (KeyError, TypeError, InvalidOperation):
        return Decimal(0)


def usable_itineraries(body: dict) -> list[dict]:
    """Priced trips that do not need a self-managed transfer."""
    return [
        item
        for item in body.get("itineraries") or []
        if _amount(item) > 0 and not item.get("requires_self_transfer")
    ]


def cheapest_itinerary(body: dict) -> dict | None:
    return min(usable_itineraries(body), key=_amount, default=None)


def steady_itinerary(body: dict) -> dict | None:
    """The cheapest trip on one airline both ways, the likeliest single booking."""
    same = [
        item
        for item in usable_itineraries(body)
        if not item.get("has_mixed_carriers")
        and item.get("inbound")
        and item["outbound"].get("carrier") == item["inbound"].get("carrier")
    ]
    return min(same, key=_amount, default=None)


def other_airline_itinerary(body: dict, avoid: dict) -> dict | None:
    """The cheapest one-airline trip that is not on the airline already tried."""
    carrier = avoid["outbound"].get("carrier")
    return steady_itinerary(
        {
            "itineraries": [
                item
                for item in usable_itineraries(body)
                if item["outbound"].get("carrier") != carrier
            ]
        }
    )


def _minutes(itinerary: dict) -> int:
    return sum(
        int((itinerary.get(name) or {}).get("duration_minutes") or 0)
        for name in ("outbound", "inbound")
    )


def clearly_better(
    cheaper: dict, steady: dict, saving: Decimal, extra: Decimal
) -> bool:
    """A harder trip must save real money without taking far longer."""
    return _amount(cheaper) <= _amount(steady) * (1 - saving) and Decimal(
        _minutes(cheaper)
    ) <= Decimal(_minutes(steady)) * (1 + extra)


def per_person(
    amount: Decimal | None, adults: int, price_is_total: bool
) -> Decimal | None:
    if amount is None or not price_is_total or adults <= 1:
        return amount
    return (amount / adults).quantize(Decimal("0.01"))


def _segments(part: dict) -> list[dict]:
    return [item for item in part.get("segments") or [] if isinstance(item, dict)]


def flight_numbers(part: dict) -> list[str]:
    numbers = []
    for segment in _segments(part):
        number = str(segment.get("flight_number") or "").strip()
        if number:
            code = str(segment.get("marketing_carrier_code") or "").strip()
            numbers.append(f"{code} {number}".strip())
    return numbers


def carrier_codes(*parts: dict) -> set[str]:
    return {
        str(segment[name]).upper()
        for part in parts
        for segment in _segments(part)
        for name in ("marketing_carrier_code", "operating_carrier_code")
        if segment.get(name)
    }


def _url_date(url: str, parameter: str) -> date | None:
    match = re.search(rf"[?&#]{parameter}=([^&#]+)", unquote(url), re.IGNORECASE)
    if match is None:
        return None
    for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(match.group(1), pattern).date()
        except ValueError:
            continue
    return None


def without_tracking(url: str) -> str:
    """Remove ad-click ids. The fragment holds real booking details on some sites."""
    cleaned = re.sub(
        r"(?<=[?&])(?:gclid|gclsrc)=[^&#]*&?", "", url, flags=re.IGNORECASE
    )
    # A removed last parameter can leave a dangling ? or & before the fragment.
    return re.sub(r"[?&]+(?=#|$)", "", cleaned)


# An airline's own site can sell only that airline. Other sellers cannot be checked.
AIRLINE_SITES = {
    "aegeanair.com": "A3",
    "airarabia.com": "G9",
    "airfrance.com": "AF",
    "ajet.com": "VF",
    "britishairways.com": "BA",
    "egyptair.com": "MS",
    "emirates.com": "EK",
    "etihad.com": "EY",
    "flyadeal.com": "F3",
    "flydubai.com": "FZ",
    "flynas.com": "XY",
    "gulfair.com": "GF",
    "kuwaitairways.com": "KU",
    "lufthansa.com": "LH",
    "omanair.com": "WY",
    "qatarairways.com": "QR",
    "rj.com": "RJ",
    "saudia.com": "SV",
    "turkishairlines.com": "TK",
}


def seller_matches(url: str, codes: set[str]) -> bool:
    """Reject another airline's site, such as flynas for a Gulf Air flight."""
    if not codes:
        return True
    host = (urlsplit(url).hostname or "").casefold()
    for site, code in AIRLINE_SITES.items():
        if host == site or host.endswith(f".{site}"):
            return code in codes
    return True


def link_matches(url: str, directions: set[str], query: FlightQuery) -> bool:
    """Reject a link whose own parameters contradict its direction or dates."""
    if not url.startswith("https://") or len(url) > MAX_BOOKING_URL_LENGTH:
        return False
    # These only accept a posted form, so opening them cannot show the flight.
    if re.search(r"posthandler|\.axd(?:$|\?)|\.ashx(?:$|\?)", url, re.IGNORECASE):
        return False
    origin, destination = query.origin_airport, query.destination_airport
    if directions == {"inbound"}:
        origin, destination = query.return_origin, query.origin_airport
    for pattern, expected in (
        (r"[?&#:,](?:origin|org)[=:]([A-Z]{3})\b", origin),
        (r"[?&#:,](?:destination|dst)[=:]([A-Z]{3})\b", destination),
    ):
        found = re.search(pattern, unquote(url), re.IGNORECASE)
        if found and found.group(1).upper() != expected:
            return False
    both = len(directions) == 2
    mode = re.search(r"flightMode=(\w+)", url, re.IGNORECASE)
    if mode and (mode.group(1).casefold() == "oneway") == both:
        return False
    expected = query.return_date if directions == {"inbound"} else query.departure_date
    departure = _url_date(url, "departureDate")
    if departure is not None and departure != expected:
        return False
    if both:
        back = _url_date(url, "returnDate")
        if back is not None and back != query.return_date:
            return False
    return True


def link_is_exact(link: dict, numbers: list[str]) -> bool:
    """Does it open this flight? Most links do not say, so check for its number."""
    stated = link.get("specificity")
    if stated:
        return stated == "exact_flight"
    url = str(link.get("url") or "").upper()
    return bool(numbers) and all(item.replace(" ", "") in url for item in numbers)


def _link_amount(link: dict | None, currency: str | None = None) -> Decimal | None:
    price = (link or {}).get("price") or {}
    try:
        amount = Decimal(str(price.get("amount")))
    except InvalidOperation:
        return None
    if amount <= 0 or (currency and str(price.get("currency")).upper() != currency):
        return None
    return amount


def pick_link(
    options: list[dict],
    directions: set[str],
    query: FlightQuery,
    codes: set[str] | None = None,
    numbers: list[str] | None = None,
) -> dict | None:
    """A valid link for these directions: the airline, then this flight, then price."""
    links = [
        link
        for option in options
        if set(option.get("legs") or []) == directions
        for link in option.get("links") or []
        if link_matches(str(link.get("url") or ""), directions, query)
        and seller_matches(str(link.get("url") or ""), codes or set())
    ]
    links.sort(
        key=lambda link: (
            link.get("provider_type") != "airline",
            not link_is_exact(link, numbers or []),
            _link_amount(link) or Decimal("Infinity"),
        )
    )
    return links[0] if links else None


def cheapest_agent(
    options: list[dict], query: FlightQuery, currency: str
) -> dict | None:
    """The cheapest agent's valid link for the whole trip, with a stated price."""
    both = {"outbound", "inbound"}
    agents = [
        link
        for option in options
        if set(option.get("legs") or []) == both
        for link in option.get("links") or []
        if link.get("provider_type") == "third_party"
        and link_matches(str(link.get("url") or ""), both, query)
        and _link_amount(link, currency)
    ]
    return min(agents, key=lambda link: _link_amount(link, currency), default=None)


def _any_price(options: list[dict], direction: str) -> dict | None:
    """A leg's price from any link. A link that cannot open still states one."""
    for option in options:
        if set(option.get("legs") or []) == {direction}:
            for link in option.get("links") or []:
                if link.get("price"):
                    return link
    return None


def _party_amount(amount: object, adults: int, price_is_total: bool) -> str:
    if not price_is_total or adults <= 1:
        return str(amount)
    return str((Decimal(str(amount)) / adults).quantize(Decimal("0.01")))


def _leg(
    direction: Literal["outbound", "return"],
    on: date,
    part: dict,
    link: dict | None,
    priced: bool,
    adults: int = 1,
    price_is_total: bool = False,
    priced_by: dict | None = None,
) -> FareLeg:
    price = ((priced_by or link) or {}).get("price") if priced else None
    segments = _segments(part)
    return FareLeg(
        direction=direction,
        date=on.isoformat(),
        airline=part.get("carrier"),
        duration_minutes=part.get("duration_minutes"),
        amount=_party_amount(price["amount"], adults, price_is_total)
        if price
        else None,
        currency=str(price["currency"]).upper() if price else None,
        booking_url=without_tracking(str(link["url"])) if link else None,
        flight_number=", ".join(flight_numbers(part)) or None,
        departure_time=segments[0].get("departure_time_local") if segments else None,
        arrival_time=segments[-1].get("arrival_time_local") if segments else None,
        # A nonstop leg has one segment; a connection has two or more.
        stops=len(segments) - 1 if segments else None,
        seller=(link or {}).get("provider_name"),
        stop_airports=tuple(
            str(item["arrival_airport"])
            for item in segments[:-1]
            if item.get("arrival_airport")
        ),
    )


def fare_from_itinerary(
    choice: dict, links: dict, query: FlightQuery, price_is_total: bool = False
) -> FlightFare:
    """Classify the trip from which booking options Ignav returned."""
    options = links.get("booking_options") or []
    outbound, inbound = choice["outbound"], choice.get("inbound")
    out_codes = carrier_codes(outbound)
    back_codes = carrier_codes(inbound) if inbound else set()
    out_numbers = flight_numbers(outbound)
    back_numbers = flight_numbers(inbound) if inbound else []
    whole = (
        pick_link(
            options,
            {"outbound", "inbound"},
            query,
            out_codes | back_codes,
            out_numbers + back_numbers,
        )
        if inbound
        else None
    )
    out_link = pick_link(options, {"outbound"}, query, out_codes, out_numbers)
    back_link = pick_link(options, {"inbound"}, query, back_codes, back_numbers)
    extra = (query.adults, price_is_total)
    if not (whole or out_link or back_link):
        raise IgnavError("no_booking_link")

    price = choice["price"]
    currency = str(price["currency"]).upper()
    amount = Decimal(str(price["amount"]))
    source: Literal["seller", "search"] = "search"
    if whole:
        trip_type = "round_trip"
        seller_price = _link_amount(whole, currency)
        if seller_price:
            amount, source = seller_price, "seller"
        # Only when a seller states each direction and they add up. Never divided.
        out_part = _any_price(options, "outbound")
        back_part = _any_price(options, "inbound")
        parts_known = [
            _link_amount(out_part, currency),
            _link_amount(back_part, currency),
        ]
        adds_up = all(parts_known) and abs(sum(parts_known) - amount) <= 1
        legs = (
            _leg(
                "outbound",
                query.departure_date,
                outbound,
                whole,
                adds_up,
                *extra,
                priced_by=out_part,
            ),
            _leg(
                "return",
                query.return_date,
                inbound,
                whole,
                adds_up,
                *extra,
                priced_by=back_part,
            ),
        )
    elif inbound:
        trip_type = "split"
        legs = (
            _leg(
                "outbound",
                query.departure_date,
                outbound,
                out_link,
                True,
                *extra,
                priced_by=None if out_link else _any_price(options, "outbound"),
            ),
            _leg(
                "return",
                query.return_date,
                inbound,
                back_link,
                True,
                *extra,
                priced_by=None if back_link else _any_price(options, "inbound"),
            ),
        )
        both = [_link_amount(out_link, currency), _link_amount(back_link, currency)]
        if all(both):
            amount, source = sum(both), "seller"
    else:
        if out_link is None:
            raise IgnavError("no_booking_link")
        trip_type = "one_way"
        legs = (
            _leg("outbound", query.departure_date, outbound, out_link, True, *extra),
        )
        seller_price = _link_amount(out_link, currency)
        if seller_price:
            amount, source = seller_price, "seller"

    provider = whole or out_link or back_link
    parts = (whole,) if whole else tuple(item for item in (out_link, back_link) if item)
    numbers = (
        out_numbers + back_numbers
        if whole
        else (out_numbers if out_link else []) + (back_numbers if back_link else [])
    )
    exact = (
        link_is_exact(whole, numbers)
        if whole
        else all(
            link_is_exact(link, flights)
            for link, flights in ((out_link, out_numbers), (back_link, back_numbers))
            if link
        )
    )
    agent = cheapest_agent(options, query, currency) if whole else None
    if provider.get("provider_type") != "airline":
        agent = None
    bags = choice.get("bags") or {}
    status = provider.get("price", {}).get("status") if source == "seller" else None
    return FlightFare(
        airline=str(outbound["carrier"]),
        duration_minutes=int(outbound["duration_minutes"]),
        amount=_party_amount(amount, query.adults, price_is_total),
        currency=currency,
        verified=trip_type == "round_trip"
        and (status or price.get("status")) == "verified",
        provider_name=str(provider.get("provider_name") or "Ignav"),
        trip_type=trip_type,
        legs=legs,
        search_amount=_party_amount(price["amount"], query.adults, price_is_total),
        price_source=source,
        exact=exact,
        seller_type=provider.get("provider_type"),
        fare_name=next(
            (item["fare_name"] for item in parts if item.get("fare_name")), None
        ),
        cabin_class=choice.get("cabin_class"),
        checked_bags=bags.get("checked"),
        carry_on_bags=bags.get("carry_on"),
        agent_name=str(agent.get("provider_name") or "") or None if agent else None,
        agent_url=without_tracking(str(agent["url"])) if agent else None,
        agent_amount=(
            _party_amount(_link_amount(agent, currency), query.adults, price_is_total)
            if agent
            else None
        ),
    )


def get_flight_provider(
    settings: Settings, cache: FareCache | None = None, verify: bool = False
) -> FlightPriceProvider:
    """verify: also require Google Flights to list each kept flight (research only,
    not the quick availability probes, to save requests)."""
    if settings.flight_price_provider == "ignav" and settings.ignav_api_key:
        usage = FlightUsage(settings.flight_usage_db)
        accuracy = PriceAccuracy(
            settings.price_accuracy_db, settings.price_gap_log_percent
        )
        return IgnavProvider(
            settings.ignav_api_key,
            cache,
            price_is_total=settings.ignav_price_scope == "total",
            split_min_saving_percent=settings.split_min_saving_percent,
            split_max_extra_duration_percent=settings.split_max_extra_duration_percent,
            on_request=lambda kind: usage.record(kind, "generation", False),
            on_fare=lambda fare, query: accuracy.record(
                fare.airline,
                f"{query.origin_airport}-{query.destination_airport}",
                fare.accuracy_gap(),
            ),
            price_conflict_percent=settings.price_conflict_percent,
            cache_seconds=settings.flight_cache_minutes * 60,
            verifier=_verifier(settings) if verify else None,
        )
    return WebSearchOnly()


def _verifier(settings: Settings):
    from app.services.google_flights_check import google_flights_check

    return google_flights_check(settings)


def fare_quote(fare: FlightFare, query: FlightQuery) -> str:
    """The evidence text: what the provider returned, written out for readers."""
    kind = {
        "round_trip": "round trip on one booking",
        "split": "round trip on separate bookings",
        "one_way": "outbound only, return not included",
    }[fare.trip_type]
    return (
        f"{fare.airline}: {fare.amount} {fare.currency} {kind}, "
        f"{query.origin_airport}-{query.destination_airport}"
        + (f", home from {query.return_origin}" if query.open_jaw else "")
        + f", {query.departure_date} to {query.return_date}, via Ignav."
    )


def format_duration(minutes: int) -> str:
    return f"{minutes // 60}h {minutes % 60}m"
