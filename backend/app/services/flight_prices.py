"""Swappable flight fare sources. Returning None means use the web search instead."""

import hashlib
import logging
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal, Protocol
from urllib.parse import unquote

import httpx2 as httpx

from app.core.config import Settings

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
    def __init__(
        self,
        api_key: str,
        cache: FareCache | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.cache = cache
        self.transport = transport
        self.requests_made = 0

    async def _post(self, path: str, body: dict) -> dict:
        self.requests_made += 1
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
        return await self._post(
            "/fares/round-trip",
            {
                "origin": query.origin_airport,
                "destination": query.destination_airport,
                "departure_date": query.departure_date.isoformat(),
                "return_date": query.return_date.isoformat(),
                "adults": 1,
                "market": "SA",
            },
        )

    async def find(self, query: FlightQuery) -> FlightFare | None:
        key = hashlib.sha256(f"ignav-legs|{query}".encode()).hexdigest()
        cached = self.cache.get(key) if self.cache else None
        if cached:
            saved = dict(cached[0])
            saved["legs"] = tuple(FareLeg(**leg) for leg in saved["legs"])
            return FlightFare(**saved)
        try:
            body = await self.search(query)
            choice = cheapest_itinerary(body)
            if choice is None:
                logger.info("flight_provider_fallback reason=no_itinerary")
                return None
            links = await self._post(
                "/fares/booking-links", {"ignav_id": str(choice["ignav_id"])}
            )
            fare = fare_from_itinerary(choice, links, query)
        except IgnavError as error:
            logger.info("flight_provider_fallback reason=%s", error)
            return None
        except (KeyError, TypeError, ValueError, AttributeError):
            logger.info("flight_provider_fallback reason=unexpected_response")
            return None
        if self.cache:
            self.cache.put(key, [asdict(fare)])
        return fare


def cheapest_itinerary(body: dict) -> dict | None:
    """The cheapest priced trip that does not need a self-managed transfer."""

    def amount(itinerary: dict) -> Decimal:
        try:
            return Decimal(str(itinerary["price"]["amount"]))
        except (KeyError, TypeError, InvalidOperation):
            return Decimal(0)

    usable = [
        item
        for item in body.get("itineraries") or []
        if amount(item) > 0 and not item.get("requires_self_transfer")
    ]
    return min(usable, key=amount) if usable else None


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


def link_matches(url: str, directions: set[str], query: FlightQuery) -> bool:
    """Reject a link whose own parameters contradict its direction or dates."""
    if not url.startswith("https://") or len(url) > MAX_BOOKING_URL_LENGTH:
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


def _pick_link(
    options: list[dict], directions: set[str], query: FlightQuery
) -> dict | None:
    """The first valid link for these directions, preferring an exact flight."""
    links = [
        link
        for option in options
        if set(option.get("legs") or []) == directions
        for link in option.get("links") or []
        if link_matches(str(link.get("url") or ""), directions, query)
    ]
    links.sort(key=lambda link: link.get("specificity") != "exact_flight")
    return links[0] if links else None


def _leg(
    direction: Literal["outbound", "return"],
    on: date,
    part: dict,
    link: dict | None,
    priced: bool,
) -> FareLeg:
    price = (link or {}).get("price") if priced else None
    return FareLeg(
        direction=direction,
        date=on.isoformat(),
        airline=part.get("carrier"),
        duration_minutes=part.get("duration_minutes"),
        amount=str(price["amount"]) if price else None,
        currency=str(price["currency"]).upper() if price else None,
        booking_url=without_tracking(str(link["url"])) if link else None,
    )


def fare_from_itinerary(choice: dict, links: dict, query: FlightQuery) -> FlightFare:
    """Classify the trip from which booking options Ignav returned."""
    options = links.get("booking_options") or []
    outbound, inbound = choice["outbound"], choice.get("inbound")
    whole = _pick_link(options, {"outbound", "inbound"}, query) if inbound else None
    out_link = _pick_link(options, {"outbound"}, query)
    back_link = _pick_link(options, {"inbound"}, query)
    if not (whole or out_link or back_link):
        raise IgnavError("no_booking_link")

    if whole:
        trip_type = "round_trip"
        legs = (
            _leg("outbound", query.departure_date, outbound, whole, False),
            _leg("return", query.return_date, inbound, whole, False),
        )
    elif inbound:
        trip_type = "split"
        legs = (
            _leg("outbound", query.departure_date, outbound, out_link, True),
            _leg("return", query.return_date, inbound, back_link, True),
        )
    else:
        if out_link is None:
            raise IgnavError("no_booking_link")
        trip_type = "one_way"
        legs = (_leg("outbound", query.departure_date, outbound, out_link, True),)

    price = choice["price"]
    provider = whole or out_link or back_link
    return FlightFare(
        airline=str(outbound["carrier"]),
        duration_minutes=int(outbound["duration_minutes"]),
        amount=str(price["amount"]),
        currency=str(price["currency"]).upper(),
        verified=trip_type == "round_trip" and price.get("status") == "verified",
        provider_name=str(provider.get("provider_name") or "Ignav"),
        trip_type=trip_type,
        legs=legs,
    )


def get_flight_provider(
    settings: Settings, cache: FareCache | None = None
) -> FlightPriceProvider:
    if settings.flight_price_provider == "ignav" and settings.ignav_api_key:
        return IgnavProvider(settings.ignav_api_key, cache)
    return WebSearchOnly()


def fare_quote(fare: FlightFare, query: FlightQuery) -> str:
    """The evidence text: what the provider returned, written out for readers."""
    kind = {
        "round_trip": "round trip on one booking",
        "split": "round trip on separate bookings",
        "one_way": "outbound only, return not included",
    }[fare.trip_type]
    return (
        f"{fare.airline}: {fare.amount} {fare.currency} {kind}, "
        f"{query.origin_airport}-{query.destination_airport}, "
        f"{query.departure_date} to {query.return_date}, via Ignav."
    )


def format_duration(minutes: int) -> str:
    return f"{minutes // 60}h {minutes % 60}m"
