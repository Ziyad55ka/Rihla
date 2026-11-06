"""Adversarial round-trip source and refreshed-quote checks. No real requests."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import httpx2 as httpx
import pytest

from app.services import flight_refresh
from app.services.flight_prices import FlightQuery, complete_return_fare
from app.services.google_flights_check import (
    GoogleFlightsCheck,
    SellerLink,
    _has_schedule,
    _sellers,
)
from tests.proposals.test_flight_prices import provider_with
from tests.proposals.test_flight_refresh import FakeIgnav, GoogleSays, book, proposal
from tests.proposals.test_flight_refresh import checker as flight_checker
from tests.proposals.test_seller_link import (
    BACK,
    OUT,
    QUERY,
    checker,
    forwards_to,
    page,
)


def test_backup_finds_a_party_round_trip_with_one_seller_total():
    check = checker(
        page(("Etihad", True, 4500)),
        forwards_to("https://digital.etihad.com/book?adults=3"),
    )
    fare, answered = asyncio.run(check.fare(QUERY))
    assert answered and fare is not None
    assert fare.amount == "1500.00"
    assert complete_return_fare(fare, QUERY)
    assert fare.schedule_confirmed and fare.price_source == "seller"


def test_backup_never_accepts_a_seller_link_for_the_wrong_party():
    check = checker(
        page(("Etihad", True, 4500)),
        forwards_to("https://digital.etihad.com/book?adults=1"),
    )
    fare, answered = asyncio.run(check.fare(QUERY))
    assert not answered and fare is None


@pytest.mark.parametrize(
    "body,absence_known",
    [
        ({"best_flights": []}, True),
        ({"best_flights": [{"flights": OUT["flights"]}]}, False),
    ],
)
def test_empty_results_and_missing_booking_tokens_are_not_the_same(body, absence_known):
    check = GoogleFlightsCheck(
        "fake", httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    )
    assert asyncio.run(check.fare(QUERY)) == (None, absence_known)


@pytest.mark.parametrize("answered", [True, False])
def test_secondary_source_failure_never_becomes_no_flights(answered):
    provider, requests = provider_with(
        httpx.Response(424, json={"error": {"code": "unable_to_complete_request"}})
    )

    class Backup:
        async def fare(self, query):
            assert query == QUERY
            return None, answered

    provider.backup = Backup()
    assert asyncio.run(provider.find(QUERY)) is None
    assert len(requests) == 3
    assert (QUERY in provider.unavailable_queries) is (not answered)
    assert provider.miss_reasons.get(QUERY) == ("no_seats" if answered else None)


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "-Infinity", "-1", "0"])
def test_invalid_seller_money_is_not_a_quote(amount):
    # The airline link can remain a navigation option with no quoted price.
    result = _sellers(page(("Etihad", True, amount)))
    assert all(price is None for _, price, _ in result)


@pytest.mark.parametrize(
    "broken", ["airport_gap", "impossible_connection", "missing_connection_clock"]
)
def test_independent_confirmation_requires_a_real_connected_schedule(broken):
    out = deepcopy(OUT)
    assert _has_schedule(out)
    if broken == "airport_gap":
        out["flights"][1]["departure_airport"]["id"] = "DXB"
    elif broken == "impossible_connection":
        out["flights"][1]["departure_airport"]["time"] = "2026-12-17 11:30"
    else:
        out["flights"][1]["departure_airport"].pop("time")
    assert not _has_schedule(out)
    assert _has_schedule(BACK)


def test_google_refresh_replaces_both_links_time_and_source_metadata(monkeypatch):
    item = proposal()
    route = item.flights[0]
    route.legs[0].flight_number = "GF162"
    route.legs[1].flight_number = "GF163"
    route.priced_at = datetime(2026, 1, 1, tzinfo=UTC)
    route.provider = "ignav"
    query = FlightQuery("RUH", "BAH", item.start_date, item.end_date, 2)

    async def seller(*args):
        return SellerLink(
            "https://www.gulfair.com/joint?adults=2", "Gulf Air", Decimal(2400), True
        )

    monkeypatch.setattr(flight_refresh, "seller_link", seller)
    check = SimpleNamespace(
        verifier=object(), settings=SimpleNamespace(meals_per_day_sar=Decimal(150))
    )
    result = asyncio.run(
        flight_refresh._google_quote(
            check, item, route, query, "round_trip", Decimal(10000)
        )
    )
    assert result is not None and result.updated
    assert result.price_sar == Decimal(1200)
    assert result.flights.priced_at == result.checked_at
    assert result.flights.priced_at > route.priced_at
    assert result.flights.provider == "google_flights"
    assert result.flights.price_source == "seller"
    assert result.flights.fare_basis == "group"
    assert all(leg.booking_url == result.url for leg in result.flights.legs)


def test_live_seller_fractional_change_replaces_search_price_and_both_links(
    tmp_path, monkeypatch
):
    check = flight_checker(tmp_path, FakeIgnav())
    check.verifier = GoogleSays(confirmed=True, listed=None)

    async def seller(*args):
        return SellerLink(
            "https://www.gulfair.com/joint?adults=2",
            "Gulf Air",
            Decimal("1900.50"),
            True,
        )

    monkeypatch.setattr(flight_refresh, "seller_link", seller)
    result = book(check)
    assert result.price_sar == Decimal("950.25")
    assert result.flights.price_per_person.amount_sar == result.price_sar
    assert result.flights.price_source == "seller"
    assert result.provider == "google_flights"
    assert result.seller_type == "airline"
    assert all(leg.booking_url == result.url for leg in result.flights.legs)
