"""One booking is a business rule, even when two one-way tickets cost less."""

import asyncio
import json
import time
from dataclasses import asdict, replace

import httpx2 as httpx
import pytest

from app.services.flight_booking_policy import complete_ground_route, single_booking
from app.services.flight_prices import complete_return_fare, link_matches
from tests.proposals.test_flight_prices import (
    LINKS,
    QUERY,
    fare,
    itinerary,
    option,
    provider_with,
)

SPLIT = {"booking_options": [option(["outbound"]), option(["inbound"])]}


@pytest.mark.parametrize(
    "kind,urls",
    [
        ("split", ["https://a.test/joint"] * 2),
        ("one_way", ["https://a.test/joint"] * 2),
        ("round_trip", ["https://a.test/out", "https://a.test/back"]),
        ("round_trip", ["https://a.test/joint"]),
        ("round_trip", [None, None]),
        ("round_trip", ["http://a.test/joint"] * 2),
        ("round_trip", ["https://user:pass@a.test/joint"] * 2),
        ("round_trip", ["https://a.test/\njoint"] * 2),
        ("round_trip", ["https://[bad/joint"] * 2),
    ],
)
def test_rejects_separate_incomplete_or_unsafe_bookings(kind, urls):
    assert not single_booking(kind, urls)


def test_opaque_joint_booking_is_accepted_without_inventing_parameters():
    assert single_booking("round_trip", ["https://a.test/opaque/123"] * 2)


@pytest.mark.parametrize("kind", ["split", "one_way"])
def test_two_matching_links_cannot_upgrade_a_separate_fare(kind):
    assert not complete_return_fare(replace(fare(), trip_type=kind), QUERY)


def test_more_expensive_joint_ticket_on_the_same_airline_is_tried():
    provider, requests = provider_with(
        httpx.Response(200, json={"itineraries": [itinerary(100), itinerary(1200)]}),
        httpx.Response(200, json=SPLIT),
        httpx.Response(200, json=LINKS),
    )
    found = asyncio.run(provider.find(QUERY))
    assert found is not None and found.amount == "1200"
    assert complete_return_fare(found, QUERY)
    assert [json.loads(r.content)["ignav_id"] for r in requests[1:]] == [
        "id-100",
        "id-1200",
    ]


def test_only_separate_tickets_stop_after_three_candidates():
    provider, requests = provider_with(
        httpx.Response(200, json={"itineraries": [itinerary(n) for n in range(1, 8)]}),
        *(httpx.Response(200, json=SPLIT) for _ in range(3)),
    )
    assert asyncio.run(provider.find(QUERY)) is None
    assert len(requests) == 4  # one search, three distinct booking-link requests
    assert len({json.loads(r.content)["ignav_id"] for r in requests[1:]}) == 3


def test_a_cached_split_fare_is_never_reused():
    class StaleCache:
        def get(self, key):
            saved = asdict(replace(fare(), trip_type="split"))
            return [{**saved, "cached_at": time.time()}]

        def put(self, key, results):
            self.saved = results

    provider, requests = provider_with(
        httpx.Response(200, json={"itineraries": [itinerary(1200)]}),
        httpx.Response(200, json=LINKS),
    )
    provider.cache = StaleCache()
    found = asyncio.run(provider.find(QUERY))
    assert len(requests) == 2
    assert found is not None and found.trip_type == "round_trip"


@pytest.mark.parametrize(
    "url,valid",
    [
        ("https://a.test/?TripType=OneWay", False),
        ("https://a.test/?TripType=RoundTrip", True),
        ("https://a.test/?PaxADT=2", False),
        (
            "https://www.turkishairlines.com/?dep=RUH&dst=CAI"
            "&depd=131226&retd=171226&pas=A%3A1%2CC%3A0",
            True,
        ),
        ("https://www.turkishairlines.com/?dep=JED", False),
        ("https://www.turkishairlines.com/?depd=141226", False),
        ("https://www.turkishairlines.com/?retd=181226", False),
        ("https://www.turkishairlines.com/?pas=A%3A2", False),
        (
            "https://book.omanair.com/?Origin1=RUH&Destination1=CAI"
            "&Origin2=CAI&Destination2=RUH&DepartureDate1=2026-12-13"
            "&DepartureDate2=2026-12-17&PaxADT=1",
            True,
        ),
        ("https://book.omanair.com/?Origin2=MCT", False),
        ("https://book.omanair.com/?Destination2=JED", False),
        ("https://book.omanair.com/?DepartureDate2=2026-12-18", False),
    ],
)
def test_explicit_airline_link_parameters_cannot_contradict_the_request(url, valid):
    assert link_matches(url, {"outbound", "inbound"}, QUERY) is valid


def test_one_booking_can_be_a_real_open_jaw():
    query = replace(QUERY, return_from_airport="MCT")
    url = "https://book.omanair.com/?Origin1=RUH&Destination1=CAI&Origin2=MCT&Destination2=RUH"
    assert link_matches(url, {"outbound", "inbound"}, query)
    original = fare()
    joint = replace(
        original, legs=tuple(replace(leg, booking_url=url) for leg in original.legs)
    )
    assert complete_return_fare(joint, query)


@pytest.mark.parametrize(
    "cities,arrival,back,valid",
    [
        (["Istanbul"], "IST", None, True),
        (["Istanbul", "Bursa"], "IST", None, False),
        (["Istanbul", "Bursa"], "IST", "IST", False),
        (["Istanbul", "Bursa", "Istanbul"], "IST", None, True),
        (["Istanbul", "Bursa", " ISTANBUL "], "IST", "IST", True),
        (["Paris", "Barcelona"], "CDG", "BCN", True),
        (["Cairo", "Alexandria"], "CAI", "CAI", False),
        (["القاهرة", "الإسكندرية", "القاهرة"], "CAI", None, True),
    ],
)
def test_multicity_trip_accounts_for_the_return_to_the_booked_airport(
    cities, arrival, back, valid
):
    assert complete_ground_route(cities, arrival, back) is valid
