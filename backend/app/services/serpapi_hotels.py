"""Google Hotels through SerpApi: a real price per night in SAR, with a link.

SerpApi is a paid, licensed search API (free plan: 250 searches a month), so Rihla
never scrapes a booking site itself. Off unless SERPAPI_API_KEY is set.

One search finds a well-rated central hotel. When SERPAPI_HOTEL_DETAILS is on, one
more request opens that hotel's Google page, whose seller list can hold Booking.com's
own price and link. Booking.com is preferred because members asked for its price.
Docs: https://serpapi.com/google-hotels-api
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx2 as httpx

from app.services.tripcom_provider import HotelOffer, HotelQuery

logger = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search"
PREFERRED_SELLER = "booking.com"
GOOGLE_HOTELS = "Google Hotels"


def _sar(value: Any) -> Decimal | None:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return amount.quantize(Decimal("0.01")) if amount > 0 else None


def _night_price(item: dict) -> Decimal | None:
    rate = item.get("rate_per_night") or {}
    return _sar(rate.get("extracted_lowest"))


def _https(url: Any) -> str | None:
    text = str(url or "")
    return text if text.startswith("https://") and len(text) <= 2000 else None


def pick_property(body: dict) -> dict | None:
    """The first hotel (not a rental) with a price; search order is Google's."""
    for item in body.get("properties") or []:
        if item.get("type", "hotel") != "hotel":
            continue
        if _night_price(item) is not None and item.get("name"):
            return item
    return None


def pick_seller(details: dict) -> tuple[str, Decimal, str] | None:
    """Booking.com's own price and link when listed, otherwise the cheapest seller."""
    sellers = []
    for key in ("featured_prices", "prices"):
        for item in details.get(key) or []:
            url = _https(item.get("link"))
            price = _night_price(item)
            name = str(item.get("source") or "").strip()
            if url and price is not None and name:
                sellers.append((name, price, url))
    if not sellers:
        return None
    for seller in sellers:
        if PREFERRED_SELLER in seller[0].casefold():
            return seller
    return min(sellers, key=lambda item: item[1])


class SerpApiHotels:
    name = "serpapi"

    def __init__(
        self,
        api_key: str,
        details: bool = True,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.details = details
        self.transport = transport
        self.requests_made = 0

    async def _get(self, params: dict) -> dict | None:
        self.requests_made += 1
        try:
            async with httpx.AsyncClient(
                timeout=60.0, trust_env=False, transport=self.transport
            ) as client:
                response = await client.get(
                    SERPAPI_URL, params={**params, "api_key": self.api_key}
                )
        except httpx.RequestError:
            logger.info("hotel_source_failed source=serpapi reason=unreachable")
            return None
        if response.status_code != 200:
            logger.info(
                "hotel_source_failed source=serpapi reason=http_%s",
                response.status_code,
            )
            return None
        try:
            body = response.json()
        except ValueError:
            return None
        if body.get("error"):
            # SerpApi says "no results" this way too, so it is not an outage.
            logger.info("hotel_source_failed source=serpapi reason=error_field")
            return None
        return body

    async def find(self, query: HotelQuery) -> HotelOffer | None:
        place = f"{query.city}, {query.country}" if query.country else query.city
        common = {
            "engine": "google_hotels",
            "check_in_date": query.check_in.isoformat(),
            "check_out_date": query.check_out.isoformat(),
            "adults": 2,
            "currency": "SAR",
            "gl": "sa",
            "hl": "en",
        }
        # [ASSUMPTION] A 3-4 star hotel rated 4.0+ fits a group trip; shown as a
        # suggestion, never as the only choice.
        body = await self._get(
            {
                **common,
                "q": f"central hotels in {place}",
                "hotel_class": "3,4",
                "rating": "8",
            }
        )
        found = pick_property(body or {})
        if found is None:
            body = await self._get({**common, "q": f"hotels in {place}"})
            found = pick_property(body or {})
        if found is None:
            return None

        name = str(found["name"]).strip()[:150]
        price = _night_price(found)
        url = _https(found.get("link"))
        source = GOOGLE_HOTELS
        exact = False
        token = found.get("property_token")
        if self.details and token:
            details = await self._get({**common, "q": place, "property_token": token})
            seller = pick_seller(details or {})
            if seller is not None:
                source, price, url = seller
                exact = True
        if url is None or price is None:
            return None
        return HotelOffer(
            name=name,
            price_sar=price,
            url=url,
            source=(source if source == GOOGLE_HOTELS else f"{source} via Google")[:50],
            exact_price=exact,
        )
