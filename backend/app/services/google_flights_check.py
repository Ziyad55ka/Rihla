"""A second source check that the itinerary is listed on Google Flights.

Why: Ignav once listed Riyadh Air RX 531 on a day the airline no longer flew it from
Riyadh, so the booking page showed nothing. A flight is kept only when Google Flights
also lists the same flight
numbers on the same day, both ways. This goes through SerpApi (the hotel key).

Each answer is True (listed), False (not listed) or None (could not check). Only False
removes a flight: an outage or a missing key must never hide every trip.
"""

import html
import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

import httpx2 as httpx

from app.services.flight_prices import (
    FareLeg,
    FlightFare,
    FlightQuery,
    complete_return_fare,
)

logger = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search.json"


def flight_key(numbers: list[str] | str | None) -> tuple[str, ...]:
    """Flight numbers in one comparable form: "RX 0531, RX 22" -> ("RX531", "RX22")."""
    if numbers is None:
        return ()
    items = numbers.split(",") if isinstance(numbers, str) else numbers
    found = []
    for item in items:
        compact = re.sub(r"\s+", "", str(item)).upper()
        match = re.fullmatch(r"([A-Z0-9]{2})0*(\d{1,4})[A-Z]?", compact)
        if match:
            found.append(match.group(1) + match.group(2))
        elif compact:
            found.append(compact)
    return tuple(found)


@dataclass(frozen=True)
class SellerLink:
    """The seller's own page with these flights and the group already chosen."""

    url: str
    seller: str
    # The seller's total for the whole group, in SAR, or None when Google hides it.
    total: Decimal | None
    airline: bool


# Google's "Continue" answers with a page that forwards to the seller.
_FORWARD = re.compile(r"""url\s*=\s*['"]?([^'">\s]+)""", re.IGNORECASE)


def forwarded_url(page: str) -> str | None:
    """The seller address in Google's forwarding page, or None."""
    match = _FORWARD.search(page)
    if not match:
        return None
    url = html.unescape(match.group(1))
    host = urlparse(url).hostname or ""
    if not url.startswith("https://") or host.endswith("google.com"):
        return None
    return url


def _options(body: dict | None) -> list[dict]:
    if not body:
        return []
    return [*(body.get("best_flights") or []), *(body.get("other_flights") or [])]


def _numbers(option: dict) -> tuple[str, ...]:
    return flight_key(
        [str(item.get("flight_number") or "") for item in option.get("flights") or []]
    )


class GoogleFlightsCheck:
    name = "google_flights"

    def __init__(
        self, api_key: str, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.api_key = api_key
        self.transport = transport
        self.requests_made = 0
        # One search per query and token while this object lives (one generation
        # or one button press), so retries cost nothing.
        self._seen: dict[str, dict | None] = {}

    async def _get(self, params: dict[str, Any]) -> dict | None:
        key = json.dumps(params, sort_keys=True)
        if key in self._seen:
            return self._seen[key]
        self.requests_made += 1
        body: dict | None = None
        try:
            async with httpx.AsyncClient(
                timeout=60.0, trust_env=False, transport=self.transport
            ) as client:
                response = await client.get(
                    SERPAPI_URL, params={**params, "api_key": self.api_key}
                )
            if response.status_code == 200:
                body = response.json()
                if not isinstance(body, dict):
                    raise ValueError("Expected an object")
                if body.get("error"):
                    # SerpApi says "no results" this way: that is an answer, not
                    # an outage, so it reads as an empty list.
                    error = str(body.get("error")).casefold()
                    body = {} if "hasn't returned any results" in error else None
                if body is not None:
                    for options_key in ("best_flights", "other_flights"):
                        options = body.get(options_key, [])
                        if not isinstance(options, list):
                            raise ValueError("Invalid flight options")
                        for option in options:
                            if not isinstance(option, dict):
                                raise ValueError("Invalid flight option")
                            flights = option.get("flights")
                            if not isinstance(flights, list) or not flights:
                                raise ValueError("Missing flight segments")
                            for flight in flights:
                                if not isinstance(flight, dict):
                                    raise ValueError("Invalid flight segment")
                                for airport in ("departure_airport", "arrival_airport"):
                                    if airport in flight and not isinstance(
                                        flight[airport], dict
                                    ):
                                        raise ValueError("Invalid airport")
            else:
                logger.info(
                    "flight_check_failed source=google_flights reason=http_%s",
                    response.status_code,
                )
        except (httpx.RequestError, ValueError):
            body = None
            logger.info("flight_check_failed source=google_flights reason=unreachable")
        self._seen[key] = body
        return body

    def _params(self, query: FlightQuery) -> dict[str, Any]:
        common: dict[str, Any] = {
            "engine": "google_flights",
            "currency": "SAR",
            "gl": "sa",
            "hl": "en",
            "adults": max(query.adults, 1),
            # The full list, as "View more flights" shows it.
            "show_hidden": "true",
        }
        if query.open_jaw:
            legs = [
                {
                    "departure_id": query.origin_airport,
                    "arrival_id": query.destination_airport,
                    "date": query.departure_date.isoformat(),
                },
                {
                    "departure_id": query.return_origin,
                    "arrival_id": query.origin_airport,
                    "date": query.return_date.isoformat(),
                },
            ]
            return {**common, "type": 3, "multi_city_json": json.dumps(legs)}
        return {
            **common,
            "type": 1,
            "departure_id": query.origin_airport,
            "arrival_id": query.destination_airport,
            "outbound_date": query.departure_date.isoformat(),
            "return_date": query.return_date.isoformat(),
        }

    async def listed_outbound(self, query: FlightQuery) -> set[tuple[str, ...]] | None:
        """The outbound flights Google Flights sells that day, or None if unknown."""
        body = await self._get(self._params(query))
        if body is None:
            return None
        return {_numbers(option) for option in _options(body)}

    async def confirm(
        self, query: FlightQuery, outbound: tuple[str, ...], inbound: tuple[str, ...]
    ) -> bool | None:
        """Both directions listed on Google Flights for these dates and airports."""
        body = await self._get(self._params(query))
        if body is None:
            return None
        matches = [o for o in _options(body) if _matches(o, outbound, query, False)]
        if not matches:
            return False
        chosen = next((o for o in matches if _has_schedule(o)), None)
        if chosen is None:
            return None
        if not inbound:
            return True
        token = chosen.get("departure_token")
        if not token:
            return None
        back = await self._get({**self._params(query), "departure_token": token})
        if back is None:
            return None
        matches = [o for o in _options(back) if _matches(o, inbound, query, True)]
        if not matches:
            return False
        return True if any(_has_schedule(o) for o in matches) else None

    async def fare(self, query: FlightQuery) -> tuple[FlightFare | None, bool]:
        """A round trip on the group's exact dates, priced by the seller for everyone.

        The second source when Ignav fails or finds nothing. Returns the fare and
        whether absence was established: (None, True) means the searched options
        were empty. Missing tokens, prices, broken links or a bounded candidate
        search are inconclusive, never evidence that there are no flights.
        """
        params = self._params(query)
        body = await self._get(params)
        if body is None:
            return None, False
        outs = sorted(
            (
                o
                for o in _options(body)
                if _on_route(o, query, False)
                and _has_schedule(o)
                and o.get("departure_token")
            ),
            key=_price,
        )
        if not outs:
            return None, not bool(_options(body))
        inconclusive = len(outs) > BACKUP_OUTBOUND_TRIES or len(outs) != len(
            _options(body)
        )
        for out in outs[:BACKUP_OUTBOUND_TRIES]:
            back_body = await self._get(
                {**params, "departure_token": out["departure_token"]}
            )
            if back_body is None:
                return None, False
            if _options(back_body):
                # Flights exist; inability to price/book one must not be reported
                # as an empty schedule, even after all candidates below fail.
                inconclusive = True
            back = min(
                (
                    o
                    for o in _options(back_body)
                    if _on_route(o, query, True) and _has_schedule(o)
                ),
                key=_price,
                default=None,
            )
            if back is None:
                continue
            booking_params = _booking_params(query, params, out, back)
            if booking_params is None:
                continue
            page = await self._get(booking_params)
            if page is None:
                return None, False
            for airline, total, together in _sellers(page):
                if total is None:
                    continue  # The price must be the seller's own, for everyone.
                url = await _follow(together["booking_request"], self.transport)
                if url:
                    link = SellerLink(
                        url, str(together.get("book_with") or ""), total, airline
                    )
                    fare = _fare_from(query, out, back, link)
                    if complete_return_fare(fare, query):
                        return fare, True
        return None, not inconclusive


# Each outbound tried costs two more requests (its returns, then its booking page).
BACKUP_OUTBOUND_TRIES = 2


def _price(option: dict) -> Decimal:
    try:
        value = Decimal(str(option.get("price")))
        return value if value.is_finite() and value > 0 else Decimal("Infinity")
    except (InvalidOperation, ValueError):
        return Decimal("Infinity")


def _local(value: object) -> str | None:
    """Google's "2026-12-01 08:30" in the form Ignav uses, 2026-12-01T08:30:00."""
    text = str(value or "")
    try:
        return datetime.fromisoformat(text).isoformat()
    except ValueError:
        return None


def _segment(flight: dict) -> tuple[str, str, str, str, str] | None:
    match = re.fullmatch(
        r"([A-Z0-9]{2})\s*0*(\d{1,4}[A-Z]?)",
        str(flight.get("flight_number") or "").strip().upper(),
    )
    start = flight.get("departure_airport") or {}
    end = flight.get("arrival_airport") or {}
    values = (
        str(start.get("id") or "").upper(),
        str(start.get("time") or "")[:10],
        str(end.get("id") or "").upper(),
        match.group(1) if match else "",
        match.group(2) if match else "",
    )
    return values if all(values) else None


def _fare_leg(direction: str, day, option: dict, link: SellerLink) -> FareLeg:
    flights = option["flights"]
    found = [_segment(item) for item in flights]
    return FareLeg(
        direction=direction,  # type: ignore[arg-type]
        date=day.isoformat(),
        airline=flights[0].get("airline"),
        duration_minutes=option.get("total_duration"),
        amount=None,
        currency=None,
        booking_url=link.url,
        flight_number=", ".join(
            str(item.get("flight_number") or "").strip() for item in flights
        )
        or None,
        departure_time=_local(flights[0]["departure_airport"].get("time")),
        arrival_time=_local(flights[-1]["arrival_airport"].get("time")),
        stops=len(flights) - 1,
        seller=link.seller or None,
        stop_airports=tuple(
            str((item.get("arrival_airport") or {}).get("id") or "")
            for item in flights[:-1]
        ),
        segments=tuple(found) if all(found) else (),  # type: ignore[arg-type]
    )


def _fare_from(
    query: FlightQuery, out: dict, back: dict, link: SellerLink
) -> FlightFare:
    assert link.total is not None
    each = (link.total / max(query.adults, 1)).quantize(Decimal("0.01"))
    return FlightFare(
        airline=str(out["flights"][0].get("airline") or link.seller),
        duration_minutes=int(out.get("total_duration") or 0),
        amount=str(each),
        currency="SAR",
        # The seller quoted this total live for both directions in one booking.
        verified=True,
        provider_name=link.seller or "Google Flights",
        trip_type="round_trip",
        legs=(
            _fare_leg("outbound", query.departure_date, out, link),
            _fare_leg("return", query.return_date, back, link),
        ),
        price_source="seller",
        exact=link.airline,
        seller_type="airline" if link.airline else "agency",
        provider="google_flights",
        observed_at=datetime.now(UTC).isoformat(timespec="seconds"),
        schedule_confirmed=True,
    )


def _has_schedule(option: dict) -> bool:
    """A flight number alone does not independently confirm its route and day."""
    flights = option.get("flights") or []
    if not flights:
        return False
    for airport in (
        airport
        for flight in flights
        for airport in (flight.get("departure_airport"), flight.get("arrival_airport"))
    ):
        if (
            not isinstance(airport, dict)
            or not airport.get("id")
            or not airport.get("time")
        ):
            return False
        try:
            datetime.fromisoformat(str(airport["time"]))
        except ValueError:
            return False
    for earlier, later in zip(flights, flights[1:], strict=False):
        arrival, departure = earlier["arrival_airport"], later["departure_airport"]
        if arrival["id"] != departure["id"]:
            return False
        try:
            # These clocks are at the same airport. Do not compare wall clocks
            # between different time zones along an international segment.
            if datetime.fromisoformat(arrival["time"]) > datetime.fromisoformat(
                departure["time"]
            ):
                return False
        except (TypeError, ValueError):
            return False
    return True


async def _follow(request: dict, transport) -> str | None:
    """Open Google's "Continue" for one seller and read where it goes."""
    url, data = request.get("url"), request.get("post_data")
    if not url or not data or not str(url).startswith("https://www.google.com/"):
        return None
    try:
        async with httpx.AsyncClient(
            timeout=20.0,
            trust_env=False,
            transport=transport,
            follow_redirects=False,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as client:
            response = await client.get(f"{url}?{data}")
    except httpx.RequestError:
        logger.info("seller_link_failed reason=unreachable")
        return None
    if 300 <= response.status_code < 400:
        found = response.headers.get("location") or ""
        return found if forwarded_url(f"url='{found}'") else None
    if response.status_code != 200:
        logger.info("seller_link_failed reason=http_%s", response.status_code)
        return None
    return forwarded_url(response.text)


def _matches(
    option: dict, numbers: tuple[str, ...], query: FlightQuery, returning: bool
) -> bool:
    return _numbers(option) == numbers and _on_route(option, query, returning)


def _on_route(option: dict, query: FlightQuery, returning: bool) -> bool:
    """The airports and day agree, and the flight home lands by the last day."""
    flights = option.get("flights") or []
    if not flights:
        return False
    origin = query.return_origin if returning else query.origin_airport
    destination = query.origin_airport if returning else query.destination_airport
    day = query.return_date if returning else query.departure_date
    first = flights[0].get("departure_airport") or {}
    last = flights[-1].get("arrival_airport") or {}
    # Validate additional structured facts when available. A matching flight
    # number alone must not override a different airport, day or late arrival.
    return not (
        (first.get("id") and first["id"] != origin)
        or (last.get("id") and last["id"] != destination)
        or (first.get("time") and str(first["time"])[:10] != day.isoformat())
        or (last.get("time") and str(last["time"])[:10] > query.return_date.isoformat())
    )


async def seller_link(
    check: "GoogleFlightsCheck",
    query: FlightQuery,
    outbound: tuple[str, ...],
    inbound: tuple[str, ...],
) -> SellerLink | None:
    """The airline's own booking page for these exact flights, for the group.

    Reuses the two searches the check already made, and asks once more for the
    booking page, where Google asks each seller live. The airline is preferred:
    its link holds the chosen flights and fare, as Etihad's did on 6 Nov 2026
    (it opened on the passenger details step with the right total).
    """
    if not isinstance(check, GoogleFlightsCheck):
        return None
    params = check._params(query)
    body = await check._get(params)
    out = next(
        (
            o
            for o in _options(body)
            if _matches(o, outbound, query, False) and _has_schedule(o)
        ),
        None,
    )
    if not out or not out.get("departure_token"):
        return None
    back_body = await check._get({**params, "departure_token": out["departure_token"]})
    back = next(
        (
            o
            for o in _options(back_body)
            if _matches(o, inbound, query, True) and _has_schedule(o)
        ),
        None,
    )
    if not back:
        return None
    booking_params = _booking_params(query, params, out, back)
    if booking_params is None:
        return None
    page = await check._get(booking_params)
    sellers = _sellers(page)
    for airline, total, together in sellers[:2]:
        url = await _follow(together["booking_request"], check.transport)
        if url:
            return SellerLink(
                url=url,
                seller=str(together.get("book_with") or ""),
                total=total,
                airline=airline,
            )
    return None


def _booking_params(
    query: FlightQuery, params: dict, outbound: dict, inbound: dict
) -> dict | None:
    """Prefer the checked token; missing tokens can pin every exact segment.

    SerpApi's documented selected_flights_json is for round trips/one ways, not
    multi-city queries. Never invent a segment or silently change query dates.
    """
    if not _on_route(outbound, query, False) or not _on_route(inbound, query, True):
        return None
    if inbound.get("booking_token"):
        return {**params, "booking_token": inbound["booking_token"]}
    if query.open_jaw or not _has_schedule(outbound) or not _has_schedule(inbound):
        return None
    selected = {}
    for direction, option in (("outbound", outbound), ("return", inbound)):
        parts = []
        for flight in option["flights"]:
            segment = _segment(flight)
            if not segment:
                return None
            origin, day, arrival, carrier, number = segment
            if not number.isdigit():
                return None
            parts.append(
                {
                    "flight_number": carrier + number,
                    "departure_id": origin,
                    "arrival_id": arrival,
                    "date": day,
                }
            )
        selected[direction] = parts
    return {
        **params,
        "selected_flights_json": json.dumps(selected, separators=(",", ":")),
    }


def _sellers(page: dict | None) -> list[tuple[bool, Decimal | None, dict]]:
    """Sellers of the whole trip in one booking: the airline first, then by price."""
    sellers = []
    for item in (page or {}).get("booking_options") or []:
        together = item.get("together") or {}
        airline = bool(together.get("airline"))
        try:
            total: Decimal | None = Decimal(str(together.get("price")))
        except (InvalidOperation, ValueError):
            total = None
        if total is not None and (not total.is_finite() or total <= 0):
            total = None
        # Google hides some airlines' prices (flynas): their own page is still best.
        if together.get("booking_request") and (total is not None or airline):
            sellers.append((airline, total, together))
    sellers.sort(key=lambda item: (not item[0], item[1] or Decimal("Infinity")))
    return sellers


def google_flights_check(settings) -> GoogleFlightsCheck | None:
    if not settings.verify_flights_on_google or not settings.serpapi_api_key:
        return None
    return GoogleFlightsCheck(settings.serpapi_api_key)
