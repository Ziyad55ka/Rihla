"""Google Hotels through SerpApi: a real price per night in SAR, with a link.

SerpApi is a paid, licensed search API (free plan: 250 searches a month), so Rihla
never scrapes a booking site itself. Off unless SERPAPI_API_KEY is set.

One search finds a well-rated central hotel. When SERPAPI_HOTEL_DETAILS is on, one
more request opens that hotel's Google page, whose seller list can hold Booking.com's
own price and link. Booking.com is preferred because members asked for its price.
Docs: https://serpapi.com/google-hotels-api
"""

import logging
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlencode, urlsplit

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
    if not amount.is_finite() or not 0 < amount <= Decimal("9999999999.99"):
        return None
    rounded = amount.quantize(Decimal("0.01"))
    return rounded if rounded > 0 else None


def _night_price(item: dict) -> Decimal | None:
    rate = item.get("rate_per_night") or {}
    if not isinstance(rate, dict):
        return None
    return _sar(rate.get("extracted_after_taxes_fees")) or _sar(
        rate.get("extracted_lowest")
    )


def _https(url: Any) -> str | None:
    text = str(url or "")
    if len(text) > 2000 or any(ord(char) < 32 for char in text):
        return None
    try:
        parts = urlsplit(text)
    except ValueError:
        return None
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
    ):
        return None
    # Search results can contain an expiring ad click, sometimes with no adurl.
    # That is not a usable hotel or seller page.
    if parts.hostname in {"google.com", "www.google.com"} and parts.path in {
        "/aclk",
        "/url",
    }:
        return None
    return text


def pick_property(body: dict, query: HotelQuery | None = None) -> dict | None:
    """The first hotel (not a rental) with a price; search order is Google's."""
    for item in body.get("properties") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type", "hotel") != "hotel":
            continue
        if (
            query
            and query.strict_stars
            and item.get("extracted_hotel_class") not in query.stars
        ):
            continue
        if _night_price(item) is not None and item.get("name"):
            return item
    return None


def average_offer(body: dict, query: HotelQuery) -> HotelOffer | None:
    """A dated market average is an allowance, never a quote for a named hotel."""
    url = _google_source(body)
    if not url:
        return None
    prices = [
        price
        for item in body.get("properties") or []
        if isinstance(item, dict)
        if item.get("type", "hotel") == "hotel"
        and (not query.strict_stars or item.get("extracted_hotel_class") in query.stars)
        if (price := _night_price(item)) is not None
    ]
    if len(prices) < 2:
        return None
    return HotelOffer(
        name=f"Comparable hotels ({len(prices)}-property average)",
        price_sar=(sum(prices) / len(prices)).quantize(Decimal("0.01")),
        url=url,
        source="Google Hotels market average",
        source_url=url,
        # No particular class is claimed for an unnamed average. Every
        # comparable above has passed the requested class filter.
        star_rating=query.stars[0] if len(query.stars) == 1 else None,
        average_sample_size=len(prices),
    )


def pick_seller(details: dict) -> tuple[str, Decimal, str] | None:
    """Booking.com's own price and link when listed, otherwise the cheapest seller."""
    sellers = []
    for key in ("featured_prices", "prices"):
        for item in details.get(key) or []:
            if not isinstance(item, dict):
                continue
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
        if not isinstance(body, dict):
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
            "hotel_class": ",".join(map(str, query.stars)),
        }
        # [ASSUMPTION] A 3-4 star hotel rated 4.0+ fits a group trip; shown as a
        # suggestion, never as the only choice.
        body = await self._get(
            {
                **common,
                "q": f"central hotels in {place}",
                "rating": "8",
            }
        )
        found = pick_property(body or {}, query)
        if found is None:
            body = await self._get({**common, "q": f"hotels in {place}"})
            found = pick_property(body or {}, query)
        if found is None:
            if body is None:
                return None
            average = average_offer(body or {}, query)
            if average:
                return average
            # A single bounded nearby-date reference can keep a good flight
            # destination useful. It is not an offer for the requested dates.
            nearby = replace(
                query,
                check_in=query.check_in + timedelta(days=7),
                check_out=query.check_out + timedelta(days=7),
            )
            reference = await self._get(
                {
                    **common,
                    "q": f"hotels in {place}",
                    "check_in_date": nearby.check_in.isoformat(),
                    "check_out_date": nearby.check_out.isoformat(),
                }
            )
            average = average_offer(reference or {}, nearby)
            if not average:
                return None
            suggested = pick_property(reference or {}, nearby)
            suggested_name = str(suggested["name"]).strip()[:150] if suggested else None
            search = "https://www.booking.com/searchresults.html?" + urlencode(
                {
                    "ss": ", ".join(
                        value for value in (suggested_name, place) if value
                    ),
                    "checkin": query.check_in.isoformat(),
                    "checkout": query.check_out.isoformat(),
                    "group_adults": 1,
                    "no_rooms": 1,
                }
            )
            return replace(
                average,
                url=search,
                source="Google Hotels nearby-date market average",
                reference_dates=(
                    nearby.check_in.isoformat(),
                    nearby.check_out.isoformat(),
                ),
                suggested_name=suggested_name,
            )

        name = str(found["name"]).strip()[:150]
        observed_url = _google_source(body or {})
        price = _night_price(found)
        url = _https(found.get("link"))
        source = GOOGLE_HOTELS
        exact = False
        token = found.get("property_token")
        if self.details and token:
            details = await self._get({**common, "q": place, "property_token": token})
            observed_url = _google_source(details or {}) or observed_url
            seller = pick_seller(details or {})
            if seller is not None:
                source, price, url = seller
                exact = True
        url = url or observed_url
        if url is None or price is None:
            return average_offer(body or {}, query)
        return HotelOffer(
            name=name,
            price_sar=price,
            url=url,
            source=(source if source == GOOGLE_HOTELS else f"{source} via Google")[:50],
            exact_price=exact,
            source_url=observed_url,
            star_rating=found.get("extracted_hotel_class"),
        )


def _google_source(body: dict) -> str | None:
    """Use the returned price page; never relabel a hotel's website as its source."""
    metadata = body.get("search_metadata") or {}
    if not isinstance(metadata, dict):
        return None
    url = _https(metadata.get("google_hotels_url"))
    if not url:
        return None
    parts = urlsplit(url)
    return (
        url
        if (
            parts.hostname in {"google.com", "www.google.com"}
            and parts.path.startswith("/travel/")
            and not parts.username
            and not parts.password
        )
        else None
    )
