"""Booking together or alone. All fakes."""

import asyncio
from dataclasses import replace
from datetime import date
from decimal import Decimal

from test_flight_refresh import (
    TRIP,
    FakeIgnav,
    book,
    checker,
    itinerary,
    proposal,
    route,
)

from app.services.flight_prices import (
    FareLeg,
    FlightFare,
    FlightQuery,
    IgnavError,
    IgnavProvider,
)
from app.services.flight_refresh import refresh_flights


class ByParty(FakeIgnav):
    """A total for the whole party when more than one person is searched."""

    def __init__(self, group: float, alone: float) -> None:
        super().__init__()
        self.prices = {True: group, False: alone}

    async def search(self, query: FlightQuery) -> dict:
        self.searches.append(query)
        amount = self.prices[query.adults > 1]
        return {"itineraries": [itinerary(amount=amount)]}


def refresh(check, adults: int, ceiling: str = "100000"):
    return asyncio.run(
        refresh_flights(
            check, proposal(), "الرياض", adults, Decimal(ceiling), TRIP, "m1"
        )
    )


def test_refresh_shows_the_cheaper_alone_price_and_budgets_on_it(tmp_path) -> None:
    fake = ByParty(group=2000, alone=900)
    check = checker(tmp_path, fake, ignav_price_scope="total")

    # 1000 for the stay plus 900 fits. The group's 1000 per person would not.
    result = refresh(check, 2, ceiling="1950")

    assert result.flights.price_per_person.amount_sar == Decimal("900.00")
    assert result.flights.fare_basis == "solo"
    assert result.flights.solo_saving_sar == Decimal("100.00")
    assert result.budget_status != "over_group_budget"
    assert [item.adults for item in fake.searches] == [2, 1]


def test_refresh_keeps_the_group_price_when_alone_is_not_cheaper(tmp_path) -> None:
    fake = ByParty(group=1801, alone=900)

    result = refresh(checker(tmp_path, fake, ignav_price_scope="total"), 2)

    assert result.flights.price_per_person.amount_sar == Decimal("900.50")
    assert result.flights.fare_basis == "group"
    assert result.flights.solo_saving_sar is None


def test_no_comparison_for_one_person(tmp_path) -> None:
    fake = ByParty(group=2000, alone=900)

    result = refresh(checker(tmp_path, fake, ignav_price_scope="total"), 1)

    assert [item.adults for item in fake.searches] == [1]
    assert result.flights.fare_basis == "group"


def test_a_failed_comparison_keeps_the_group_price(tmp_path) -> None:
    class AloneFails(ByParty):
        async def search(self, query: FlightQuery) -> dict:
            if query.adults == 1:
                raise IgnavError("http_503")
            return await super().search(query)

    fake = AloneFails(group=2000, alone=900)

    result = refresh(checker(tmp_path, fake, ignav_price_scope="total"), 2)

    assert result.flights.price_per_person.amount_sar == Decimal("1000.00")
    assert result.flights.fare_basis == "group"


def test_booking_a_solo_price_checks_the_one_person_fare(tmp_path) -> None:
    fake = ByParty(group=2000, alone=900)
    solo = route().model_copy(
        update={"fare_basis": "solo", "solo_saving_sar": Decimal("100.00")}
    )

    result = book(
        checker(tmp_path, fake, ignav_price_scope="total"),
        adults=2,
        item=proposal(solo),
    )

    assert fake.searches[0].adults == 1
    assert result.previous_price_sar is None


def _fare() -> FlightFare:
    out = FareLeg("outbound", "2026-11-20", "Gulf Air", 80, None, "SAR", None, "GF 1")
    back = replace(out, direction="return", date="2026-11-30", flight_number="GF 2")
    return FlightFare(
        "Gulf Air", 80, "1000.00", "SAR", True, "Gulf Air", "round_trip", (out, back)
    )


def _numbered(amount: float) -> dict:
    def side(number: str) -> dict:
        return {
            "carrier": "Gulf Air",
            "duration_minutes": 80,
            "segments": [{"marketing_carrier_code": "GF", "flight_number": number}],
        }

    return {
        "ignav_id": "x",
        "price": {"amount": amount, "currency": "SAR", "status": "verified"},
        "outbound": side("1"),
        "inbound": side("2"),
    }


def _generation_check(adults: int, body: dict):
    provider = IgnavProvider("fake")
    calls: list[FlightQuery] = []

    async def search(query: FlightQuery) -> dict:
        calls.append(query)
        return body

    provider.search = search
    query = FlightQuery("RUH", "BAH", date(2026, 11, 20), date(2026, 11, 30), adults)
    return asyncio.run(provider._cheaper_alone(_fare(), query)), calls


def test_generation_takes_the_cheaper_alone_fare() -> None:
    fare, calls = _generation_check(2, {"itineraries": [_numbered(900)]})

    assert calls[0].adults == 1
    assert Decimal(fare.amount) == Decimal(900)
    assert Decimal(fare.solo_saving) == Decimal(100)


def test_generation_ignores_another_flight_and_skips_one_person() -> None:
    other = _numbered(100)
    other["outbound"]["segments"][0]["flight_number"] = "9"

    fare, _ = _generation_check(2, {"itineraries": [other]})
    assert fare.solo_saving is None

    fare, calls = _generation_check(1, {"itineraries": [_numbered(900)]})
    assert calls == []
    assert fare.solo_saving is None
