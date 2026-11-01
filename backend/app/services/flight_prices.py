"""Swappable flight fare sources. Returning None means use the web search instead."""

import hashlib
import logging
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal, Protocol
from urllib.parse import unquote, urlsplit

import httpx2 as httpx

from app.core.config import Settings
from app.services.flight_usage import FlightUsage

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
        *,
        price_is_total: bool = False,
        split_min_saving_percent: Decimal = Decimal(15),
        split_max_extra_duration_percent: Decimal = Decimal(30),
        on_request: Callable[[str], None] | None = None,
    ) -> None:
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
        return await self._post("/fares/booking-links", {"ignav_id": ignav_id})

    async def _fare(self, choice: dict, query: FlightQuery) -> FlightFare | None:
        links = await self.booking_links(str(choice["ignav_id"]))
        try:
            return fare_from_itinerary(choice, links, query, self.price_is_total)
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
        saving = Decimal(fare.amount) - _amount(alone)
        if saving < 1:
            return fare
        return replace(
            fare,
            amount=str(alone["price"]["amount"]),
            verified=fare.verified and alone["price"].get("status") == "verified",
            solo_saving=str(saving),
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
            if cheapest_itinerary(body) is None:
                logger.info("flight_provider_fallback reason=no_itinerary")
                self.no_itinerary.add(query)
                return None
            fare = await self._best_fare(body, query)
            if fare is None:
                logger.info("flight_provider_fallback reason=no_booking_link")
                return None
            fare = await self._cheaper_alone(fare, query)
        except IgnavError as error:
            logger.info("flight_provider_fallback reason=%s", error)
            return None
        except (KeyError, TypeError, ValueError, AttributeError):
            logger.info("flight_provider_fallback reason=unexpected_response")
            return None
        if self.cache:
            self.cache.put(key, [asdict(fare)])
        return fare


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
        origin, destination = destination, origin
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


def pick_link(
    options: list[dict],
    directions: set[str],
    query: FlightQuery,
    codes: set[str] | None = None,
) -> dict | None:
    """The first valid link for these directions, preferring an exact flight."""
    links = [
        link
        for option in options
        if set(option.get("legs") or []) == directions
        for link in option.get("links") or []
        if link_matches(str(link.get("url") or ""), directions, query)
        and seller_matches(str(link.get("url") or ""), codes or set())
    ]
    links.sort(key=lambda link: link.get("specificity") != "exact_flight")
    return links[0] if links else None


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
) -> FareLeg:
    price = (link or {}).get("price") if priced else None
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
    )


def fare_from_itinerary(
    choice: dict, links: dict, query: FlightQuery, price_is_total: bool = False
) -> FlightFare:
    """Classify the trip from which booking options Ignav returned."""
    options = links.get("booking_options") or []
    outbound, inbound = choice["outbound"], choice.get("inbound")
    out_codes = carrier_codes(outbound)
    back_codes = carrier_codes(inbound) if inbound else set()
    whole = (
        pick_link(options, {"outbound", "inbound"}, query, out_codes | back_codes)
        if inbound
        else None
    )
    out_link = pick_link(options, {"outbound"}, query, out_codes)
    back_link = pick_link(options, {"inbound"}, query, back_codes)
    extra = (query.adults, price_is_total)
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
            _leg("outbound", query.departure_date, outbound, out_link, True, *extra),
            _leg("return", query.return_date, inbound, back_link, True, *extra),
        )
    else:
        if out_link is None:
            raise IgnavError("no_booking_link")
        trip_type = "one_way"
        legs = (
            _leg("outbound", query.departure_date, outbound, out_link, True, *extra),
        )

    price = choice["price"]
    provider = whole or out_link or back_link
    return FlightFare(
        airline=str(outbound["carrier"]),
        duration_minutes=int(outbound["duration_minutes"]),
        amount=_party_amount(price["amount"], query.adults, price_is_total),
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
        usage = FlightUsage(settings.flight_usage_db)
        return IgnavProvider(
            settings.ignav_api_key,
            cache,
            price_is_total=settings.ignav_price_scope == "total",
            split_min_saving_percent=settings.split_min_saving_percent,
            split_max_extra_duration_percent=settings.split_max_extra_duration_percent,
            on_request=lambda kind: usage.record(kind, "generation", False),
        )
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
