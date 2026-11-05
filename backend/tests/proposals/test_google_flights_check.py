"""Flights are kept only when Google Flights also sells them (Riyadh Air case)."""

import asyncio
import json
from datetime import date

import httpx2 as httpx

from app.services.flight_prices import FlightQuery, IgnavProvider
from app.services.google_flights_check import GoogleFlightsCheck, flight_key

QUERY = FlightQuery("RUH", "MAD", date(2026, 11, 8), date(2026, 11, 16), 1)


def google_option(*numbers: str, token: str | None = None) -> dict:
    option = {"flights": [{"flight_number": n} for n in numbers], "price": 2287}
    if token:
        option["departure_token"] = token
    return option


def google(outbound: list[dict], inbound: dict[str, list[dict]]):
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        calls.append(params)
        token = params.get("departure_token")
        if token:
            return httpx.Response(200, json={"best_flights": inbound.get(token, [])})
        return httpx.Response(200, json={"best_flights": outbound})

    return GoogleFlightsCheck("key", httpx.MockTransport(handler)), calls


def test_flight_numbers_compare_in_one_form() -> None:
    assert flight_key("RX 0531, RX 22") == ("RX531", "RX22")
    assert flight_key(["sv 1"]) == ("SV1",)


def test_both_directions_must_be_listed() -> None:
    check, calls = google(
        [google_option("RX 531", token="t1")], {"t1": [google_option("RX 532")]}
    )

    assert asyncio.run(check.confirm(QUERY, ("RX531",), ("RX532",))) is True
    assert asyncio.run(check.confirm(QUERY, ("RX531",), ("RX999",))) is False
    assert asyncio.run(check.confirm(QUERY, ("SV1",), ("SV2",))) is False
    # The same search and token are asked once only.
    assert len(calls) == 2
    assert calls[0]["currency"] == "SAR" and calls[0]["type"] == "1"


def test_an_outage_never_removes_a_flight() -> None:
    check = GoogleFlightsCheck(
        "key", httpx.MockTransport(lambda request: httpx.Response(503))
    )
    assert asyncio.run(check.confirm(QUERY, ("RX531",), ("RX532",))) is None
    assert asyncio.run(check.listed_outbound(QUERY)) is None


def test_open_jaw_is_checked_as_a_multi_city_search() -> None:
    check, calls = google([], {})
    asyncio.run(
        check.listed_outbound(
            FlightQuery("RUH", "CDG", date(2026, 12, 1), date(2026, 12, 8), 1, "BCN")
        )
    )
    legs = json.loads(calls[0]["multi_city_json"])
    assert calls[0]["type"] == "3"
    assert [(leg["departure_id"], leg["arrival_id"]) for leg in legs] == [
        ("RUH", "CDG"),
        ("BCN", "RUH"),
    ]


def ignav_trip(amount: int, out: str, back: str) -> dict:
    def side(number: str) -> dict:
        code, digits = number.split()
        return {
            "carrier": "Riyadh Air" if code == "RX" else "Saudia",
            "duration_minutes": 400,
            "segments": [{"flight_number": digits, "marketing_carrier_code": code}],
        }

    return {
        "price": {"amount": amount, "currency": "SAR", "status": "verified"},
        "outbound": side(out),
        "inbound": side(back),
        "requires_self_transfer": False,
        "ignav_id": f"id-{out}",
    }


LINKS = {
    "booking_options": [
        {
            "legs": ["outbound", "inbound"],
            "links": [{"provider_name": "Saudia", "url": "https://www.saudia.com/b"}],
        }
    ]
}


class FakeCheck:
    def __init__(self, listed: set, confirmed: bool | None) -> None:
        self.listed = listed
        self.confirmed = confirmed

    async def listed_outbound(self, query):
        return self.listed

    async def confirm(self, query, outbound, inbound):
        return self.confirmed


def ignav(*responses: dict, verifier=None) -> IgnavProvider:
    remaining = [httpx.Response(200, json=body) for body in responses]
    return IgnavProvider(
        "key",
        None,
        httpx.MockTransport(lambda request: remaining.pop(0)),
        verifier=verifier,
    )


def test_a_cheaper_flight_google_does_not_sell_is_skipped_for_one_it_does() -> None:
    # Riyadh Air is cheaper but no longer flies that day; Saudia is really sold.
    search = {
        "itineraries": [
            ignav_trip(2287, "RX 531", "RX 532"),
            ignav_trip(2600, "SV 227", "SV 228"),
        ]
    }
    provider = ignav(search, LINKS, verifier=FakeCheck({("SV227",)}, True))

    fare = asyncio.run(provider.find(QUERY))

    assert fare.amount == "2600"
    assert fare.legs[0].flight_number == "SV 227"
    assert fare.schedule_confirmed is True


def test_no_flight_google_sells_means_no_fare() -> None:
    search = {"itineraries": [ignav_trip(2287, "RX 531", "RX 532")]}
    provider = ignav(search, verifier=FakeCheck(set(), None))

    assert asyncio.run(provider.find(QUERY)) is None


def test_unknown_check_keeps_the_fare_but_does_not_claim_it_was_confirmed() -> None:
    search = {"itineraries": [ignav_trip(2600, "SV 227", "SV 228")]}
    provider = ignav(search, LINKS, verifier=FakeCheck({("SV227",)}, None))

    fare = asyncio.run(provider.find(QUERY))

    assert fare is not None and fare.schedule_confirmed is False
