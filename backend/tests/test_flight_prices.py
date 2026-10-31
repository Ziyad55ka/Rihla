"""Ignav tests with a fake transport. These spend no Ignav requests."""

import asyncio
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx2 as httpx
import pytest

from app.core.config import Settings
from app.services import flight_prices, trip_research
from app.services.flight_prices import (
    FlightFare,
    FlightQuery,
    IgnavProvider,
    WebSearchOnly,
    airport_for_city,
    cheapest_itinerary,
    get_flight_provider,
)
from app.services.trip_research import ResearchRequest, ResearchSource, research

QUERY = FlightQuery("RUH", "CAI", date(2026, 12, 13), date(2026, 12, 17))


def itinerary(amount, *, self_transfer=False, status="verified") -> dict:
    return {
        "price": {"amount": amount, "currency": "SAR", "status": status},
        "outbound": {"carrier": "Saudia", "duration_minutes": 200, "segments": []},
        "inbound": {"carrier": "Saudia", "duration_minutes": 210, "segments": []},
        "requires_self_transfer": self_transfer,
        "ignav_id": f"id-{amount}",
    }


LINKS = {
    "booking_options": [
        {
            "legs": [{}, {}],
            "links": [
                {"provider_name": "Saudia", "url": "https://saudia.example/book"}
            ],
        }
    ]
}


def provider_with(*responses: httpx.Response) -> tuple[IgnavProvider, list]:
    remaining = list(responses)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return remaining.pop(0)

    return IgnavProvider("secret-key", None, httpx.MockTransport(handler)), requests


def test_cities_map_to_airports() -> None:
    assert airport_for_city(" riyadh ") == "RUH"
    assert airport_for_city("جدة") == "JED"
    assert airport_for_city("Atlantis") is None


def test_cheapest_skips_self_transfer_and_unpriced() -> None:
    body = {
        "itineraries": [
            itinerary(500, self_transfer=True),
            itinerary(0),
            itinerary(900),
            itinerary(800),
        ]
    }

    assert cheapest_itinerary(body)["ignav_id"] == "id-800"


def test_find_searches_then_gets_the_booking_link() -> None:
    provider, requests = provider_with(
        httpx.Response(200, json={"itineraries": [itinerary(1450)]}),
        httpx.Response(200, json=LINKS),
    )

    fare = asyncio.run(provider.find(QUERY))

    assert fare.booking_url == "https://saudia.example/book"
    assert (fare.amount, fare.currency, fare.verified) == ("1450", "SAR", True)
    assert provider.requests_made == 2
    search = json.loads(requests[0].content)
    assert requests[0].headers["X-Api-Key"] == "secret-key"
    assert requests[0].url.path == "/api/fares/round-trip"
    assert search["market"] == "SA"
    assert search["return_date"] == "2026-12-17"
    assert json.loads(requests[1].content) == {"ignav_id": "id-1450"}


@pytest.mark.parametrize(
    "responses",
    [
        [httpx.Response(401)],
        [httpx.Response(402)],
        [httpx.Response(503)],
        [httpx.Response(200, json={"itineraries": []})],
        [httpx.Response(200, content=b"not json")],
        [
            httpx.Response(200, json={"itineraries": [itinerary(1450)]}),
            httpx.Response(404),
        ],
        [
            httpx.Response(200, json={"itineraries": [itinerary(1450)]}),
            httpx.Response(200, json={"booking_options": []}),
        ],
    ],
)
def test_any_failure_returns_none_for_fallback(responses: list) -> None:
    provider, _ = provider_with(*responses)

    assert asyncio.run(provider.find(QUERY)) is None


def test_network_failure_returns_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    provider = IgnavProvider("k", None, httpx.MockTransport(handler))

    assert asyncio.run(provider.find(QUERY)) is None


def test_provider_choice_depends_on_key_and_setting() -> None:
    no_key = Settings(_env_file=None)
    with_key = Settings(_env_file=None, ignav_api_key="k")
    forced = Settings(_env_file=None, ignav_api_key="k", flight_price_provider="tavily")

    assert isinstance(get_flight_provider(no_key), WebSearchOnly)
    assert isinstance(get_flight_provider(with_key), IgnavProvider)
    assert isinstance(get_flight_provider(forced), WebSearchOnly)


class FakeProvider:
    def __init__(self, fare: FlightFare | None) -> None:
        self.fare = fare
        self.requests_made = 2

    async def find(self, query: FlightQuery) -> FlightFare | None:
        return self.fare


def fare(amount="1450", currency="SAR", verified=True) -> FlightFare:
    return FlightFare(
        "Saudia", 200, amount, currency, verified, "https://saudia.example/b", "Saudia"
    )


def run_research(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, found: FlightFare | None
):
    searched: list[str] = []

    async def search(query, settings, cost=None):
        searched.append(query)
        return [
            ResearchSource(id=1, title="T", url="https://e.com", content="c")
        ], False

    async def extract(groups, settings, cost):
        return []

    monkeypatch.setattr(trip_research, "search_sources", search)
    monkeypatch.setattr(trip_research, "extract_facts", extract)
    monkeypatch.setattr(
        trip_research, "get_flight_provider", lambda *args: FakeProvider(found)
    )
    request = ResearchRequest(
        destination="Egypt",
        country="Egypt",
        cities=["Cairo"],
        period="December 2026",
        origins=["Riyadh"],
        arrival_airport="CAI",
        departure_date=date(2026, 12, 13),
        return_date=date(2026, 12, 17),
    )
    settings = Settings(_env_file=None, search_cache_db=tmp_path / "c.sqlite3")
    return asyncio.run(research(request, settings)), searched


def test_live_fare_is_sourced_and_replaces_the_flight_search(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result, searched = run_research(monkeypatch, tmp_path, fare())

    assert not any(query.startswith("flights") for query in searched)
    fields = {item.field_id: item for item in result.fields}
    price = fields["flights.0.price_per_person"]
    assert (price.amount_sar, price.status) == (Decimal("1450.00"), "Sourced")
    assert fields["flights.0.airline"].value == "Saudia"
    assert fields["flights.0.duration"].value == "3h 20m"
    source_id = price.evidence[0].source_id
    urls = {source.id: source.url for source in result.sources}
    assert urls[source_id] == "https://saudia.example/b"
    assert result.cost.ignav_requests == 2


def test_no_fare_falls_back_to_the_flight_search(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result, searched = run_research(monkeypatch, tmp_path, None)

    assert any(query.startswith("flights") for query in searched)
    assert "flights.0.price_per_person" in {item.field_id for item in result.fields}


@pytest.mark.parametrize(
    "found",
    [fare(amount="400", currency="USD"), fare(verified=False)],
)
def test_converted_or_unchecked_fare_is_only_estimated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, found: FlightFare
) -> None:
    result, _ = run_research(monkeypatch, tmp_path, found)

    price = {item.field_id: item for item in result.fields}[
        "flights.0.price_per_person"
    ]
    assert price.status == "Estimated"


def test_unknown_currency_falls_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, searched = run_research(monkeypatch, tmp_path, fare(currency="JPY"))

    assert any(query.startswith("flights") for query in searched)


def test_cached_fare_spends_no_request(tmp_path: Path) -> None:
    cache = trip_research.SearchCache(tmp_path / "c.sqlite3", 3600)
    provider, _ = provider_with(
        httpx.Response(200, json={"itineraries": [itinerary(1450)]}),
        httpx.Response(200, json=LINKS),
    )
    provider.cache = cache

    first = asyncio.run(provider.find(QUERY))
    made = provider.requests_made
    again = asyncio.run(provider.find(QUERY))

    assert again == first
    assert provider.requests_made == made
    assert flight_prices.format_duration(200) == "3h 20m"


@pytest.mark.parametrize(
    "option",
    [
        {"legs": [{}], "links": [{"url": "https://air.example/book"}]},
        {
            "legs": [{}, {}],
            "links": [{"url": "https://air.example/?flightMode=oneway"}],
        },
    ],
)
def test_link_for_one_direction_cannot_make_a_fare_verified(option: dict) -> None:
    provider, _ = provider_with(
        httpx.Response(200, json={"itineraries": [itinerary(729)]}),
        httpx.Response(200, json={"booking_options": [option]}),
    )

    assert asyncio.run(provider.find(QUERY)).verified is False


def test_whole_trip_link_is_preferred() -> None:
    options = [
        {"legs": [{}], "links": [{"url": "https://air.example/one"}]},
        {"legs": [{}, {}], "links": [{"url": "https://air.example/both"}]},
    ]
    provider, _ = provider_with(
        httpx.Response(200, json={"itineraries": [itinerary(729)]}),
        httpx.Response(200, json={"booking_options": options}),
    )

    fare = asyncio.run(provider.find(QUERY))

    assert fare.booking_url == "https://air.example/both"
    assert fare.verified is True
