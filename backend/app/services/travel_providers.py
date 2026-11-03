"""The sources Rihla asks for flights and hotels, and which are switched on.

A flight source returns the shape documented at https://ignav.com/docs/response-format,
so the rest of the code does not care where a fare came from: `itineraries`, each with
`price`, `outbound`, `inbound` and an id, then `booking_options` for that id. An amount
covers the whole party. Failures raise IgnavError, which holds no response body.

To add a source: write a class with these methods, add it to the builders below, and
put its name in FLIGHT_PROVIDERS or HOTEL_PROVIDERS. A paid source stays off by default,
and a source's terms must be read before it is switched on.
"""

from typing import Protocol

from app.core.config import Settings
from app.services.flight_prices import FlightQuery, IgnavProvider
from app.services.serpapi_hotels import SerpApiHotels
from app.services.tripcom_provider import (
    HotelOffer,
    HotelQuery,
    TripComFlights,
    TripComHotels,
)


class FlightProvider(Protocol):
    name: str

    async def search(self, query: FlightQuery) -> dict: ...

    async def booking_links(self, option_id: str) -> dict: ...


class HotelProvider(Protocol):
    name: str

    async def find(self, query: HotelQuery) -> HotelOffer | None: ...


def live_flight_providers(settings: Settings) -> list[FlightProvider]:
    """The sources switched on, in the configured order."""
    found: list[FlightProvider] = []
    for name in settings.flight_providers:
        if name == "tripcom" and settings.tripcom_enabled:
            found.append(TripComFlights())
        elif (
            name == "ignav"
            and settings.flight_price_provider == "ignav"
            and settings.ignav_api_key
        ):
            found.append(
                IgnavProvider(
                    settings.ignav_api_key,
                    price_conflict_percent=settings.price_conflict_percent,
                )
            )
    return found


def live_hotel_providers(settings: Settings) -> list[HotelProvider]:
    found: list[HotelProvider] = []
    names = list(settings.hotel_providers)
    # An older .env lists only tripcom; a SerpApi key alone is enough to use it.
    if settings.serpapi_api_key and "serpapi" not in names:
        names.insert(0, "serpapi")
    for name in names:
        if name == "tripcom" and settings.tripcom_enabled:
            found.append(TripComHotels())
        elif name == "serpapi" and settings.serpapi_api_key:
            found.append(
                SerpApiHotels(
                    settings.serpapi_api_key, details=settings.serpapi_hotel_details
                )
            )
    return found


async def find_hotel(
    providers: list[HotelProvider], query: HotelQuery
) -> HotelOffer | None:
    """The first source with a named hotel. A failed source passes to the next."""
    for provider in providers:
        offer = await provider.find(query)
        if offer is not None:
            return offer
    return None
