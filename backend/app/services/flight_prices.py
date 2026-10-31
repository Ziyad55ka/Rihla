"""Swappable flight fare sources. Returning None means use the web search instead."""

import hashlib
import logging
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Protocol

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
class FlightFare:
    airline: str
    duration_minutes: int
    amount: str
    currency: str
    # False when the provider has not checked this price against a live offer.
    verified: bool
    booking_url: str
    provider_name: str


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

    async def _booking_link(self, ignav_id: str) -> tuple[str, str]:
        body = await self._post("/fares/booking-links", {"ignav_id": ignav_id})
        for option in body.get("booking_options") or []:
            for link in option.get("links") or []:
                url = str(link.get("url") or "")
                if url.startswith("https://") and len(url) <= MAX_BOOKING_URL_LENGTH:
                    return url, str(link.get("provider_name") or "Ignav")
        raise IgnavError("no_booking_link")

    async def find(self, query: FlightQuery) -> FlightFare | None:
        key = hashlib.sha256(f"ignav|{query}".encode()).hexdigest()
        cached = self.cache.get(key) if self.cache else None
        if cached:
            return FlightFare(**cached[0])
        try:
            body = await self.search(query)
            choice = cheapest_itinerary(body)
            if choice is None:
                logger.info("flight_provider_fallback reason=no_itinerary")
                return None
            url, provider_name = await self._booking_link(str(choice["ignav_id"]))
            price = choice["price"]
            fare = FlightFare(
                airline=str(choice["outbound"]["carrier"]),
                duration_minutes=int(choice["outbound"]["duration_minutes"]),
                amount=str(price["amount"]),
                currency=str(price["currency"]).upper(),
                verified=price.get("status") == "verified",
                booking_url=url,
                provider_name=provider_name,
            )
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


def get_flight_provider(
    settings: Settings, cache: FareCache | None = None
) -> FlightPriceProvider:
    if settings.flight_price_provider == "ignav" and settings.ignav_api_key:
        return IgnavProvider(settings.ignav_api_key, cache)
    return WebSearchOnly()


def fare_quote(fare: FlightFare, query: FlightQuery) -> str:
    """The evidence text: what the provider returned, written out for readers."""
    return (
        f"{fare.airline}: {fare.amount} {fare.currency} round trip, "
        f"{query.origin_airport}-{query.destination_airport}, "
        f"{query.departure_date} to {query.return_date}, via Ignav."
    )


def format_duration(minutes: int) -> str:
    return f"{minutes // 60}h {minutes % 60}m"
