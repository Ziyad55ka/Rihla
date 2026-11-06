"""Adversarial supplier data and budget regressions. No outside requests."""

import asyncio
from dataclasses import replace
from decimal import Decimal

import httpx2 as httpx
import pytest

from app.core.config import Settings
from app.services import fare_first, trip_research
from app.services.flight_prices import (
    IgnavError,
    IgnavProvider,
    _link_amount,
    cheapest_itinerary,
    complete_return_fare,
    fare_from_itinerary,
    link_matches,
)
from app.services.proposal_costs import proposal_costs
from app.services.serpapi_hotels import _sar
from app.services.trip_research import ResearchCost, ResearchRequest, sar_amount
from tests.proposals.test_costs_and_compatibility import (
    context,
    istanbul,
    line,
    scenario,
)
from tests.proposals.test_fare_first import group, option
from tests.proposals.test_flight_prices import (
    LINKS,
    QUERY,
    fare,
    itinerary,
    provider_with,
)


def test_invalid_cheapest_dates_do_not_hide_next_valid_fare():
    wrong = itinerary(900)
    wrong["outbound"]["segments"] = [{"departure_time_local": "2026-12-14T09:00:00"}]
    right = itinerary(1200)
    provider, _ = provider_with(
        httpx.Response(200, json={"itineraries": [wrong, right]}),
        httpx.Response(200, json=LINKS),
    )
    result = asyncio.run(provider.find(QUERY))
    assert result is not None and Decimal(result.amount) == 1200


@pytest.mark.parametrize("body", [[], {"unexpected": []}, {"itineraries": "bad"}])
def test_malformed_source_is_unavailable_instead_of_no_flights(body):
    provider, _ = provider_with(httpx.Response(200, json=body))
    assert asyncio.run(provider.find(QUERY)) is None
    assert QUERY in provider.unavailable_queries
    assert QUERY not in provider.no_itinerary


@pytest.mark.parametrize("status", [401, 403, 429])
def test_provider_quota_or_credentials_stop_repeated_requests(status):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(status)

    provider = IgnavProvider("private", transport=httpx.MockTransport(handle))
    assert asyncio.run(provider.find(QUERY)) is None
    assert asyncio.run(provider.find(replace(QUERY, adults=2))) is None
    assert len(calls) == 1
    assert len(provider.unavailable_queries) == 2


def test_airport_change_during_connection_requires_explicit_transport():
    choice = itinerary(1200)
    choice["outbound"]["segments"] = [
        {"departure_airport": QUERY.origin_airport, "arrival_airport": "LHR"},
        {"departure_airport": "LGW", "arrival_airport": QUERY.destination_airport},
    ]
    with pytest.raises(IgnavError, match="airport_transfer_required"):
        fare_from_itinerary(choice, LINKS, QUERY)


@pytest.mark.parametrize(
    "amount", ["NaN", "sNaN", "Infinity", "-Infinity", "-1", "0", "", "unknown"]
)
def test_invalid_supplier_money_cannot_become_a_fare(amount):
    assert cheapest_itinerary({"itineraries": [itinerary(amount)]}) is None
    assert _link_amount({"price": {"amount": amount, "currency": "SAR"}}, "SAR") is None
    assert sar_amount(amount, "SAR") is None
    assert _sar(amount) is None


@pytest.mark.parametrize(
    "direction,field,value",
    [
        ("outbound", "departure_airport", "JED"),
        ("outbound", "arrival_airport", "DXB"),
        ("outbound", "departure_time_local", "2026-12-14T01:30:00"),
        ("inbound", "departure_airport", "DXB"),
        ("inbound", "arrival_airport", "JED"),
        ("inbound", "departure_time_local", "2026-12-18T01:30:00"),
    ],
)
def test_supplier_cannot_relabel_wrong_route_or_day_as_requested(
    direction, field, value
):
    choice = itinerary(1200)
    choice[direction]["segments"] = [{field: value}]
    with pytest.raises(IgnavError):
        fare_from_itinerary(choice, LINKS, QUERY)


@pytest.mark.parametrize(
    "broken",
    [
        "one_way",
        "missing_return",
        "missing_link",
        "wrong_return_day",
        "duplicate_direction",
    ],
)
def test_availability_requires_a_complete_bookable_return(broken):
    original = fare()
    assert complete_return_fare(original, QUERY)
    legs = original.legs
    if broken == "one_way":
        original = replace(original, trip_type="one_way")
    elif broken == "missing_return":
        original = replace(original, legs=legs[:1])
    elif broken == "missing_link":
        original = replace(original, legs=(legs[0], replace(legs[1], booking_url=None)))
    elif broken == "wrong_return_day":
        original = replace(
            original, legs=(legs[0], replace(legs[1], date="2026-12-18"))
        )
    else:
        original = replace(original, legs=(legs[0], legs[0]))
    assert not complete_return_fare(original, QUERY)


def test_missing_return_makes_both_person_and_group_totals_partial():
    proposal = istanbul()
    proposal.flights[0].trip_type = "one_way"
    private = context()
    private.proposals[0].flights[0].trip_type = "one_way"
    costs = proposal_costs(proposal, Decimal(0), private)
    for rooms in ("single", "shared"):
        plan = scenario(costs, rooms)
        assert line(plan, "flights").per_person.partial
        assert plan.per_person_total.partial
        assert plan.group_total.partial
        assert plan.own_budget == "unconfirmed"


def test_overnight_return_outside_travel_dates_is_not_complete():
    original = fare()
    overnight = replace(original.legs[1], arrival_time="2026-12-18T04:10:00")
    assert not complete_return_fare(
        replace(original, legs=(original.legs[0], overnight)), QUERY
    )


@pytest.mark.parametrize("parameter", ["adultCount", "adults", "adt", "PaxAdult"])
def test_booking_party_must_match_search_party(parameter):
    url = f"https://air.example/book?{parameter}=2"
    assert not link_matches(url, {"outbound", "inbound"}, QUERY)
    assert link_matches(url, {"outbound", "inbound"}, replace(QUERY, adults=2))


@pytest.mark.parametrize(
    "parameter,value", [("departure_date", "20261214"), ("return_date", "20261218")]
)
def test_compact_supplier_dates_must_match(parameter, value):
    assert not link_matches(
        f"https://air.example/book?{parameter}={value}", {"outbound", "inbound"}, QUERY
    )


def test_arabic_and_english_departure_aliases_share_one_party_query(
    tmp_path, monkeypatch
):
    queries = []

    class Provider:
        requests_made = 0

        async def find(self, query):
            queries.append(query)
            return fare()

    monkeypatch.setattr(
        trip_research, "get_flight_provider", lambda *args, **kwargs: Provider()
    )
    request = ResearchRequest(
        destination="Egypt",
        cities=["Cairo"],
        period="January",
        arrival_airport="CAI",
        departure_date=QUERY.departure_date,
        return_date=QUERY.return_date,
        travelers={"riyadh": 2, "الرياض": 3},
        require_live_fares=True,
    )
    found, _ = asyncio.run(
        trip_research._find_fares(
            request,
            ["Riyadh", "الرياض"],
            Settings(_env_file=None, search_cache_db=tmp_path / "cache.sqlite3"),
            ResearchCost(),
        )
    )
    assert len(queries) == 1
    assert queries[0].adults == 5
    assert set(found) == {0, 1}


def test_flight_source_outage_is_not_reported_as_no_seats():
    provider, _ = provider_with(httpx.Response(503))
    generation = group()
    generation.members = generation.members[:1]
    with pytest.raises(trip_research.ResearchError) as caught:
        asyncio.run(
            fare_first.probe_option(
                option("Cairo", "CAI"),
                generation,
                provider,
                generation.shared_start,
                [],
            )
        )
    assert caught.value.code == "flight_source_unavailable"


def test_unknown_departure_stops_before_model_or_flight_requests(tmp_path):
    generation = group()
    generation.members[0].departure_city = "Atlantis"
    with pytest.raises(trip_research.ResearchError) as caught:
        asyncio.run(fare_first.generate(generation, Settings(_env_file=None), 1))
    assert caught.value.code == "departure_airport_unknown"
