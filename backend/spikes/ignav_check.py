"""Spike: exactly one real Ignav search, RUH to CAI. No booking-link request.

Run from the backend folder:
    uv run python spikes/ignav_check.py
"""

import asyncio
import sys
from datetime import date

from app.core.config import Settings
from app.services.flight_prices import (
    FlightQuery,
    IgnavError,
    IgnavProvider,
    cheapest_itinerary,
)


async def main() -> None:
    settings = Settings()
    if not settings.ignav_api_key:
        sys.exit("IGNAV_API_KEY is not configured.")
    provider = IgnavProvider(settings.ignav_api_key)
    try:
        body = await provider.search(
            FlightQuery("RUH", "CAI", date(2026, 12, 13), date(2026, 12, 17))
        )
    except IgnavError as error:
        sys.exit(f"Ignav failed: {error}")
    itineraries = body.get("itineraries") or []
    print("requests:", provider.requests_made, "| itineraries:", len(itineraries))
    print("statuses:", sorted({str(i["price"].get("status")) for i in itineraries}))
    choice = cheapest_itinerary(body)
    if choice is None:
        sys.exit("No usable itinerary.")
    print("price:", choice["price"])
    print(
        "outbound:",
        choice["outbound"]["carrier"],
        choice["outbound"]["duration_minutes"],
    )
    print(
        "inbound:", choice["inbound"]["carrier"], choice["inbound"]["duration_minutes"]
    )
    print(
        "self transfer:",
        choice["requires_self_transfer"],
        "| has id:",
        bool(choice["ignav_id"]),
    )


asyncio.run(main())
