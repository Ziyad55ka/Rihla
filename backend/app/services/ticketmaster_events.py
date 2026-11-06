"""Optional structured events, independent of the language model.

Discovery listings are not seat reservations. Only dated, currently on-sale public
events in the requested city/country survive. The upper advertised price is used
as an estimate; missing prices never become free tickets. No response or API key
is logged. One bounded request per city keeps academic usage predictable.
"""

import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

import httpx2 as httpx

logger = logging.getLogger(__name__)
URL = "https://app.ticketmaster.com/discovery/v2/events.json"

# Conservative coverage: unknown/ambiguous locations use the existing research
# flow. We never search every country and call the first matching city correct.
COUNTRIES = {
    "france": "FR",
    "فرنسا": "FR",
    "united kingdom": "GB",
    "uk": "GB",
    "بريطانيا": "GB",
    "spain": "ES",
    "إسبانيا": "ES",
    "اسبانيا": "ES",
    "germany": "DE",
    "ألمانيا": "DE",
    "italy": "IT",
    "إيطاليا": "IT",
    "united states": "US",
    "usa": "US",
    "الولايات المتحدة": "US",
    "canada": "CA",
    "كندا": "CA",
    "australia": "AU",
    "أستراليا": "AU",
    "saudi arabia": "SA",
    "السعودية": "SA",
    "uae": "AE",
    "الإمارات": "AE",
    "egypt": "EG",
    "مصر": "EG",
    "qatar": "QA",
    "قطر": "QA",
    "japan": "JP",
    "اليابان": "JP",
    "netherlands": "NL",
    "هولندا": "NL",
}
CITIES = {
    "paris": ("Paris", "FR"),
    "باريس": ("Paris", "FR"),
    "london": ("London", "GB"),
    "لندن": ("London", "GB"),
    "madrid": ("Madrid", "ES"),
    "مدريد": ("Madrid", "ES"),
    "barcelona": ("Barcelona", "ES"),
    "برشلونة": ("Barcelona", "ES"),
    "rome": ("Rome", "IT"),
    "روما": ("Rome", "IT"),
    "berlin": ("Berlin", "DE"),
    "برلين": ("Berlin", "DE"),
    "amsterdam": ("Amsterdam", "NL"),
    "أمستردام": ("Amsterdam", "NL"),
    "new york": ("New York", "US"),
    "نيويورك": ("New York", "US"),
    "dubai": ("Dubai", "AE"),
    "دبي": ("Dubai", "AE"),
    "riyadh": ("Riyadh", "SA"),
    "الرياض": ("Riyadh", "SA"),
    "jeddah": ("Jeddah", "SA"),
    "جدة": ("Jeddah", "SA"),
}


def normalized(value: str) -> str:
    return " ".join(
        "".join(
            c
            for c in unicodedata.normalize("NFKD", value)
            if not unicodedata.combining(c)
        )
        .casefold()
        .split()
    )


def location(city: str, destination: str) -> tuple[str, str] | None:
    country = COUNTRIES.get(normalized(destination))
    known = CITIES.get(normalized(city))
    if known:
        return known[0], country or known[1]
    if country:
        return city, country
    return None


@dataclass(frozen=True)
class EventListing:
    id: str
    name: str
    city: str
    venue: str
    day: date
    url: str
    amount: Decimal | None
    currency: str | None

    @property
    def content(self) -> str:
        price = (
            f"Advertised upper ticket price {self.amount} {self.currency}. "
            if self.amount is not None
            else "Ticket price unavailable. "
        )
        return (
            f"{self.name}. {self.day.isoformat()}. {self.venue}, {self.city}. "
            f"{price}Listing status: on sale. Seats and final fees are not confirmed."
        )[:500]


def _instant(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp must have a timezone")
    return parsed


def _price(ranges: list[dict]) -> tuple[Decimal | None, str | None]:
    # Mixed currencies or partially malformed ranges cannot be compared safely.
    if not ranges:
        return None, None
    try:
        currencies = {str(item["currency"]).upper() for item in ranges}
        upper = [Decimal(str(item["max"])) for item in ranges]
        lower = [Decimal(str(item["min"])) for item in ranges]
        if len(currencies) != 1 or not all(
            low.is_finite() and high.is_finite() and 0 <= low <= high <= 1_000_000
            for low, high in zip(lower, upper, strict=True)
        ):
            return None, None
        return max(upper), currencies.pop()
    except (KeyError, TypeError, InvalidOperation):
        return None, None


def parse_event(
    item: dict, city: str, country: str, start: date, end: date, now: datetime
) -> EventListing | None:
    try:
        dates = item["dates"]
        when = dates["start"]
        if dates["status"]["code"] != "onsale" or any(
            when.get(flag)
            for flag in ("dateTBD", "dateTBA", "timeTBA", "noSpecificTime")
        ):
            return None
        day = date.fromisoformat(when["localDate"])
        if not start <= day <= end:
            return None
        instant = _instant(when.get("dateTime"))
        if instant and instant <= now:
            return None
        sales = item.get("sales", {}).get("public", {})
        sale_start, sale_end = (
            _instant(sales.get("startDateTime")),
            _instant(sales.get("endDateTime")),
        )
        if (
            sales.get("startTBD")
            or (sale_start and sale_start > now)
            or (sale_end and sale_end <= now)
        ):
            return None
        venues = item["_embedded"]["venues"]
        # A listing with ambiguous venues is not a precise city suggestion.
        if len(venues) != 1:
            return None
        venue = venues[0]
        actual_city = venue["city"]["name"]
        if (
            normalized(actual_city) != normalized(city)
            or venue["country"]["countryCode"] != country
        ):
            return None
        url = item["url"]
        parts = urlsplit(url)
        host = (parts.hostname or "").casefold()
        # Official Ticketmaster country sites and documented Discovery sources.
        trusted = bool(
            re.fullmatch(
                r"(?:www\.)?ticketmaster\.(?:com|co\.uk|ca|fr|de|es|it|nl|ie|com\.au|co\.nz)",
                host,
            )
        )
        trusted |= any(
            host == d or host.endswith("." + d)
            for d in ("universe.com", "frontgatetickets.com")
        )
        if (
            parts.scheme != "https"
            or parts.username
            or parts.password
            or not trusted
            or len(url) > 2000
        ):
            return None
        name, venue_name = str(item["name"]).strip(), str(venue["name"]).strip()
        identifier = str(item["id"]).strip()
        if (
            not identifier
            or not name
            or len(name) > 150
            or not venue_name
            or len(venue_name) > 100
        ):
            return None
        amount, currency = _price(item.get("priceRanges") or [])
        return EventListing(
            identifier, name, actual_city, venue_name, day, url, amount, currency
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


class TicketmasterEvents:
    def __init__(self, api_key: str, transport: httpx.AsyncBaseTransport | None = None):
        self.api_key = api_key
        self.transport = transport

    async def find(
        self, city: str, destination: str, start: date, end: date
    ) -> list[EventListing]:
        place = location(city, destination)
        if not place:
            return []
        city_name, country = place
        params = {
            "apikey": self.api_key,
            "city": city_name,
            "countryCode": country,
            "localStartDateTime": f"{start}T00:00:00,{end}T23:59:59",
            "includeTBA": "no",
            "includeTBD": "no",
            "includeTest": "no",
            "size": 20,
            "page": 0,
            "sort": "relevance,desc",
        }
        try:
            async with httpx.AsyncClient(
                timeout=20, trust_env=False, transport=self.transport
            ) as client:
                response = await client.get(URL, params=params)
            response.raise_for_status()
            body = response.json()
            items = body.get("_embedded", {}).get("events", [])
            if not isinstance(items, list):
                raise ValueError("Invalid events response")
        except (httpx.HTTPError, ValueError, AttributeError):
            # Deliberately no URL, response body, exception text or credentials.
            logger.info("activity_source_failed source=ticketmaster")
            raise EventsUnavailable from None
        now = datetime.now(UTC)
        found, seen = [], set()
        for item in items[:20]:
            event = parse_event(item, city_name, country, start, end, now)
            if event and event.id not in seen:
                found.append(event)
                seen.add(event.id)
        return found


class EventsUnavailable(Exception):
    """A failed source is distinct from a successful search with no events."""
