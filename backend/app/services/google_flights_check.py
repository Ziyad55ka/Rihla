"""A second, independent check that a flight is really sold, on Google Flights.

Why: Ignav once listed Riyadh Air RX 531 on a day the airline no longer flew it from
Riyadh, so the booking page showed nothing. Google Flights reads airline schedules and
seats directly, so a flight is kept only when Google Flights also lists the same flight
numbers on the same day, both ways. This goes through SerpApi (the hotel key).

Each answer is True (listed), False (not listed) or None (could not check). Only False
removes a flight: an outage or a missing key must never hide every trip.
"""

import json
import logging
import re
from typing import Any

import httpx2 as httpx

from app.services.flight_prices import FlightQuery

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
                if body.get("error"):
                    # SerpApi says "no results" this way: that is an answer, not
                    # an outage, so it reads as an empty list.
                    error = str(body.get("error")).casefold()
                    body = {} if "hasn't returned any results" in error else None
            else:
                logger.info(
                    "flight_check_failed source=google_flights reason=http_%s",
                    response.status_code,
                )
        except (httpx.RequestError, ValueError):
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
        chosen = next((o for o in _options(body) if _numbers(o) == outbound), None)
        if chosen is None:
            return False
        if not inbound:
            return True
        token = chosen.get("departure_token")
        if not token:
            return None
        back = await self._get({**self._params(query), "departure_token": token})
        if back is None:
            return None
        return any(_numbers(option) == inbound for option in _options(back))


def google_flights_check(settings) -> GoogleFlightsCheck | None:
    if not settings.verify_flights_on_google or not settings.serpapi_api_key:
        return None
    return GoogleFlightsCheck(settings.serpapi_api_key)
