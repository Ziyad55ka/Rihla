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
    FareLeg,
    FlightFare,
    FlightQuery,
    IgnavProvider,
    WebSearchOnly,
    airport_for_city,
    cheapest_itinerary,
    fare_from_itinerary,
    get_flight_provider,
    link_matches,
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


def option(legs, url="https://air.example/book", price=None, name="Saudia") -> dict:
    return {
        "legs": legs,
        "links": [{"provider_name": name, "url": url, "price": price}],
    }


LINKS = {"booking_options": [option(["outbound", "inbound"])]}


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

    assert fare.source_url == "https://air.example/book"
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
    url = "https://saudia.example/b"
    return FlightFare(
        "Saudia",
        200,
        amount,
        currency,
        verified,
        "Saudia",
        "round_trip",
        (
            FareLeg("outbound", "2026-12-13", "Saudia", 200, None, None, url),
            FareLeg("return", "2026-12-17", "Saudia", 210, None, None, url),
        ),
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


SAR = {"amount": 300, "currency": "SAR", "status": "verified"}


def classify(links: dict, choice: dict | None = None) -> FlightFare:
    return fare_from_itinerary(choice or itinerary(729), links, QUERY)


def test_one_option_for_both_directions_is_round_trip() -> None:
    found = classify(LINKS)

    assert found.trip_type == "round_trip"
    assert found.verified is True
    assert [leg.direction for leg in found.legs] == ["outbound", "return"]
    assert found.legs[0].booking_url == found.legs[1].booking_url
    assert found.legs[1].date == "2026-12-17"
    assert found.legs[0].amount is None


def test_separate_options_are_split_with_their_own_link_and_price() -> None:
    found = classify(
        {
            "booking_options": [
                option(["outbound"], "https://a.example/out", SAR),
                option(["inbound"], "https://b.example/back", SAR),
            ]
        }
    )

    assert found.trip_type == "split"
    assert found.verified is False
    assert found.legs[0].booking_url == "https://a.example/out"
    assert found.legs[1].booking_url == "https://b.example/back"
    assert found.legs[1].amount == "300"


def test_real_cairo_link_is_split_with_no_return_link() -> None:
    url = (
        "https://booking.flynas.com/#/booking/search-redirect?origin=RUH"
        "&destination=CAI&departureDate=12%2F13%2F2026&returnDate=12%2F13%2F2026"
        "&flightMode=oneway"
    )

    found = classify({"booking_options": [option(["outbound"], url)]})

    assert found.trip_type == "split"
    assert found.legs[0].booking_url == url
    assert found.legs[1].booking_url is None
    assert found.verified is False


def test_no_return_flight_is_one_way() -> None:
    choice = itinerary(500)
    choice["inbound"] = None

    found = classify({"booking_options": [option(["outbound"], price=SAR)]}, choice)

    assert found.trip_type == "one_way"
    assert len(found.legs) == 1


@pytest.mark.parametrize(
    ("directions", "url", "valid"),
    [
        ({"outbound", "inbound"}, "https://a.example/?flightMode=oneway", False),
        ({"outbound"}, "https://a.example/?flightMode=round", False),
        ({"outbound"}, "https://a.example/#x?departureDate=12%2F13%2F2026", True),
        ({"outbound"}, "https://a.example/?departureDate=12%2F14%2F2026", False),
        ({"inbound"}, "https://a.example/?departureDate=2026-12-17", True),
        ({"inbound"}, "https://a.example/?departureDate=2026-12-13", False),
        (
            {"outbound", "inbound"},
            "https://a.example/?departureDate=2026-12-13&returnDate=2026-12-13",
            False,
        ),
        ({"outbound"}, "http://a.example/", False),
    ],
)
def test_link_must_match_its_direction_and_date(
    directions: set, url: str, valid: bool
) -> None:
    assert link_matches(url, directions, QUERY) is valid


def test_link_with_wrong_date_is_dropped_and_leaves_null() -> None:
    found = classify(
        {
            "booking_options": [
                option(["outbound"], "https://a.example/out"),
                option(["inbound"], "https://b.example/?departureDate=2026-12-13"),
            ]
        }
    )

    assert found.legs[1].booking_url is None


def test_exact_flight_link_is_preferred() -> None:
    links = {
        "booking_options": [
            {
                "legs": ["outbound", "inbound"],
                "links": [
                    {
                        "url": "https://a.example/search",
                        "specificity": "search_results",
                    },
                    {"url": "https://a.example/exact", "specificity": "exact_flight"},
                ],
            }
        ]
    }

    assert classify(links).legs[0].booking_url == "https://a.example/exact"
