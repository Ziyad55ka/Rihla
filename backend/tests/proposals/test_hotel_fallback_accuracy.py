import asyncio
from dataclasses import replace
from decimal import Decimal

import httpx2 as httpx

from app.services import proposal_generation, trip_research
from app.services.serpapi_hotels import SerpApiHotels
from tests.proposals.test_proposal_generation import (
    fake_research,
    group,
    option,
    settings,
)
from tests.proposals.test_serpapi_hotels import STAY


def test_nearby_average_does_not_claim_requested_date_availability():
    seen = []

    def handle(request):
        seen.append(dict(request.url.params))
        properties = (
            []
            if len(seen) < 3
            else [
                {
                    "type": "hotel",
                    "name": f"Reference {price}",
                    "extracted_hotel_class": 4,
                    "rate_per_night": {"extracted_lowest": price},
                }
                for price in [400, 600]
            ]
        )
        return httpx.Response(
            200,
            json={
                "properties": properties,
                "search_metadata": {
                    "google_hotels_url": "https://www.google.com/travel/hotels/reference"
                },
            },
        )

    query = replace(STAY, stars=(4,), strict_stars=True)
    offer = asyncio.run(
        SerpApiHotels("fake", transport=httpx.MockTransport(handle)).find(query)
    )
    assert offer and offer.price_sar == Decimal(500)
    assert offer.reference_dates == ("2026-11-27", "2026-12-01")
    assert offer.suggested_name == "Reference 400"
    assert "checkin=2026-11-20" in offer.url and "checkout=2026-11-24" in offer.url
    assert not offer.exact_price
    fields = trip_research._hotel_placeholders(
        trip_research.ResearchRequest(
            destination="Doha",
            cities=["Doha"],
            origins=["Riyadh"],
            period="November 2026",
        ),
        {0: offer},
        [],
    )
    sources = []
    trip_research._apply_hotel_sources({0: offer}, fields, sources)
    price = next(f for f in fields if f.category == "hotel_price")
    name = next(f for f in fields if f.category == "hotel_name")
    assert name.value == "Reference 400" and name.status == "Unconfirmed"
    assert price.status == "Unconfirmed" and price.amount_sar == 500
    assert "availability and price are not confirmed" in sources[0].content


def test_hotel_source_timeout_returns_planning_fallback_without_blocking_flights(
    monkeypatch, tmp_path
):
    cancelled = []

    async def slow(*args):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(True)

    monkeypatch.setattr(trip_research, "_find_hotel_offers", slow)
    monkeypatch.setattr(trip_research, "HOTEL_SEARCH_TIMEOUT_SECONDS", 0.001)
    result = asyncio.run(
        trip_research._bounded_hotel_offers(
            trip_research.ResearchRequest(
                destination="Doha",
                cities=["Doha"],
                origins=["Riyadh"],
                period="November 2026",
            ),
            settings(tmp_path),
        )
    )
    assert result == {} and cancelled == [True]


def test_missing_hotel_keeps_flight_destination_with_honest_nightly_estimate(
    tmp_path, monkeypatch
):
    generation = group(
        accommodation={"value": "stay:stars=5;lower=;notes:", "importance": "Essential"}
    )
    for member in generation.members:
        member.max_budget_sar = Decimal(10000)

    async def research(request, config):
        result = await fake_research()(request, config)
        result.hotel_stars = {}
        return result

    monkeypatch.setattr(trip_research, "research", research)
    plan = option("Paris")
    plan.cities[0].typical_hotel_night_sar = 420
    result = asyncio.run(
        proposal_generation._research_option(
            plan,
            1,
            generation,
            [],
            [],
            ["Riyadh", "Jeddah"],
            1,
            settings(tmp_path),
            trip_research.ResearchCost(),
        )
    )
    assert result.flights and all(f.trip_type == "round_trip" for f in result.flights)
    assert result.cities[0].hotel_name.value is None
    assert result.cities[0].hotel_price_per_night.amount_sar == Decimal(420)
    assert result.cities[0].hotel_price_per_night.status == "Unconfirmed"
    assert result.cities[0].hotel_stars is None
    assert result.cities[0].booking_url.startswith(
        "https://www.booking.com/searchresults"
    )
    assert result.budget_status == "includes_unconfirmed"
