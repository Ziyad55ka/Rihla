"""Trip.com's AI plugin API, off by default (TRIPCOM_ENABLED).

Written from the OpenAPI file archived on 1 May 2026, because the published address and
these routes returned 404 on 1 November 2026. A failed call passes to the next source.
Used for a non-commercial academic project only, and Trip.com must be named next to
whatever comes from it. Links are used exactly as returned, never built by Rihla.
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx2 as httpx

from app.services.flight_prices import FlightQuery, IgnavError

TRIPCOM_BASE_URL = "https://www.trip.com/ai-resource"
TRIPCOM_NAME = "Trip.com"
FLIGHT_CODE = re.compile(r"\b([A-Z0-9]{2})\s*(\d{1,4})\b")


@dataclass(frozen=True)
class HotelQuery:
    city: str
    check_in: date
    check_out: date
    # Named in searches so that Alexandria, Egypt is not Alexandria, Virginia.
    country: str | None = None


@dataclass(frozen=True)
class HotelOffer:
    name: str
    # Assumed per night for one room. The file does not say, so it stays an estimate.
    price_sar: Decimal | None
    url: str | None
    # Shown to the user next to the price and link.
    source: str
    address: str | None = None
    # True when the price is what the seller showed for these exact dates.
    exact_price: bool = False


async def _post(
    path: str, body: dict, transport: httpx.AsyncBaseTransport | None
) -> dict:
    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            trust_env=False,
            transport=transport,
            headers={"User-Agent": "Rihla-academic-project/1.0"},
        ) as client:
            response = await client.post(f"{TRIPCOM_BASE_URL}{path}", json=body)
    except httpx.RequestError as error:
        raise IgnavError("unreachable") from error
    if response.status_code != 200:
        raise IgnavError(f"http_{response.status_code}")
    try:
        found = response.json()
    except ValueError as error:
        raise IgnavError("invalid_json") from error
    if not isinstance(found, dict):
        raise IgnavError("invalid_json")
    return found


def _minutes(text: Any) -> int:
    """Reads "1h 20m" or "80m". The file does not fix this field's format."""
    found = re.fullmatch(
        r"(?:(\d+)\s*h)?\s*(?:(\d+)\s*m(?:in)?)?", str(text or "").strip()
    )
    if not found or not any(found.groups()):
        return 0
    return int(found.group(1) or 0) * 60 + int(found.group(2) or 0)


def _side(flight: dict, prefix: str = "") -> dict | None:
    def field(name: str) -> Any:
        key = f"{prefix}{name[0].upper()}{name[1:]}" if prefix else name
        return flight.get(key)

    if not field("airline") and not field("flightNumber"):
        return None
    numbers = FLIGHT_CODE.findall(str(field("flightNumber") or "").upper())
    segments = [
        {"marketing_carrier_code": code, "flight_number": number}
        for code, number in numbers
    ]
    if segments:
        segments[0]["departure_time_local"] = field("departureTime")
        segments[-1]["arrival_time_local"] = field("arrivalTime")
    return {
        "carrier": str(field("airline") or ""),
        "duration_minutes": _minutes(field("flightDuration")),
        "segments": segments,
    }


class TripComFlights:
    """One request per search. Links come with it, so they cost nothing more."""

    name = "tripcom"

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.transport = transport
        self.links: dict[str, dict] = {}
        self.requests_made = 0

    async def search(self, query: FlightQuery) -> dict:
        self.requests_made += 1
        text = (
            f"Round trip flights from {query.origin_airport} to "
            f"{query.destination_airport}, {query.departure_date} "
            f"to {query.return_date}"
        )
        body = await _post(
            "/searchFlightTicket",
            {
                "originCityCode": query.origin_airport,
                "destinationCityCode": query.destination_airport,
                "departureDate": query.departure_date.isoformat(),
                "returnDate": query.return_date.isoformat(),
                "locale": "en-XX",
                "oneWayOrRoundTrip": "RT",
                "originalInput": text,
                "originalInputInEnglish": text,
            },
            self.transport,
        )
        itineraries = []
        for index, flight in enumerate(body.get("recommendedListOfOtherFlights") or []):
            option = self._itinerary(index, flight, query.adults)
            if option is not None:
                itineraries.append(option)
        return {"observed_at": None, "itineraries": itineraries}

    def _itinerary(self, index: int, flight: dict, adults: int) -> dict | None:
        outbound, inbound = _side(flight), _side(flight, "return")
        try:
            ticket = Decimal(str(flight.get("pricePerTicket")))
        except InvalidOperation:
            return None
        if outbound is None or ticket <= 0:
            return None
        # The API has no passenger count and prices one ticket. Others are per party.
        price = {
            "amount": str(ticket * adults),
            "currency": str(flight.get("currency") or "").upper(),
            "status": "unverified",
        }
        option_id = f"tripcom-{index}"
        url = str(flight.get("flightTicketLink") or "")
        self.links[option_id] = {
            "booking_options": [
                {
                    "legs": ["outbound", "inbound"] if inbound else ["outbound"],
                    "links": [
                        {
                            "provider_name": TRIPCOM_NAME,
                            "provider_type": "third_party",
                            "price": price,
                            "url": url,
                        }
                    ],
                }
            ]
            if url
            else []
        }
        return {
            "ignav_id": option_id,
            "price": price,
            "outbound": outbound,
            "inbound": inbound,
            "has_mixed_carriers": False,
        }

    async def booking_links(self, option_id: str) -> dict:
        return self.links.get(option_id, {"booking_options": []})


class TripComHotels:
    name = "tripcom"

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.transport = transport

    async def find(self, query: HotelQuery) -> HotelOffer | None:
        text = f"Hotels in {query.city}, {query.check_in} to {query.check_out}"
        try:
            body = await _post(
                "/searchHotel",
                {
                    "cityName": query.city,
                    "topHotel": 5,
                    "locale": "en-XX",
                    "checkIn": query.check_in.isoformat(),
                    "checkOut": query.check_out.isoformat(),
                    "originalInput": text,
                    "originalInputInEnglish": text,
                },
                self.transport,
            )
        except IgnavError:
            return None
        for hotel in body.get("hotelList") or []:
            name = str(hotel.get("hotelName") or "").strip()
            amount = _sar(hotel.get("hotelPrice"), hotel.get("hotelCurrency"))
            if name and amount is not None:
                return HotelOffer(
                    name=name[:150],
                    price_sar=amount,
                    url=_https(hotel.get("hotelLink")),
                    source=TRIPCOM_NAME,
                    address=str(hotel.get("hotelAddress") or "")[:200] or None,
                )
        return None


def _https(url: Any) -> str | None:
    text = str(url or "")
    return text if text.startswith("https://") and len(text) <= 2000 else None


def _sar(amount: Any, currency: Any) -> Decimal | None:
    """Only riyals. Any other currency needs a rate this source does not give."""
    if str(currency or "").upper() != "SAR":
        return None
    try:
        value = Decimal(str(amount))
    except InvalidOperation:
        return None
    return value.quantize(Decimal("0.01")) if value > 0 else None
