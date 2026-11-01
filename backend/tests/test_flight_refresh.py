"""The light flight update, with a fake Ignav. Spends no real requests."""

import asyncio
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import httpx2 as httpx
import pytest

from app.core.config import Settings
from app.schemas.proposals import (
    CityStay,
    Evidence,
    FlightLeg,
    Flights,
    InfoField,
    Proposal,
    ProposalSource,
    SarPrice,
)
from app.services import flight_refresh, trip_research
from app.services.flight_prices import (
    FlightQuery,
    IgnavError,
    IgnavProvider,
    clearly_better,
    link_matches,
    seller_matches,
)
from app.services.flight_refresh import (
    FlightChecker,
    NoRoute,
    book_flight,
    refresh_flights,
)
from app.services.flight_usage import FlightUsage

TRIP = "00000000-0000-4000-8000-0000000000aa"
QUOTE = "Gulf Air: 900 SAR round trip, RUH-BAH, 2026-11-20 to 2026-11-30, via Ignav."
EVIDENCE = [Evidence(source_id=1, quote=QUOTE)]


def info(value: str) -> InfoField:
    return InfoField(value=value, status="Sourced", evidence=EVIDENCE)


NO_PRICE = SarPrice(amount_sar=None, status="Not available", evidence=[])


def leg(
    direction: str, day: date, carrier: str, amount: str | None = None
) -> FlightLeg:
    return FlightLeg(
        direction=direction,
        date=day,
        airline=info(carrier),
        duration=info("1h 20m"),
        price=(
            SarPrice(amount_sar=amount, status="Estimated", evidence=EVIDENCE)
            if amount
            else NO_PRICE
        ),
        booking_url=None,
    )


def route(trip_type: str = "round_trip", amount: str = "900") -> Flights:
    prices = ("500", "400") if trip_type == "split" else (None, None)
    return Flights(
        origin="الرياض",
        trip_type=trip_type,
        legs=[
            leg("outbound", date(2026, 11, 20), "Gulf Air", prices[0]),
            leg("return", date(2026, 11, 30), "Gulf Air", prices[1]),
        ],
        airline=info("Gulf Air"),
        duration=info("1h 20m"),
        price_per_person=SarPrice(
            amount_sar=amount, status="Estimated", evidence=EVIDENCE
        ),
    )


def proposal(flights: Flights | None = None) -> Proposal:
    return Proposal(
        id=UUID("00000000-0000-4000-8000-0000000000bb"),
        trip_id=UUID(TRIP),
        version=1,
        option_number=1,
        title="Trip",
        destination="Bahrain",
        start_date=date(2026, 11, 20),
        end_date=date(2026, 11, 30),
        cities=[
            CityStay(
                order=1,
                city="Manama",
                nights=10,
                hotel_name=InfoField(value=None, status="Not available", evidence=[]),
                hotel_price_per_night=SarPrice(
                    amount_sar="100", status="Estimated", evidence=EVIDENCE
                ),
                booking_url=None,
            )
        ],
        flights=[flights or route()],
        intercity_transport=[],
        flexible_adjustments=[],
        budget_status="within_group_budget",
        sources=[ProposalSource(id=1, title="T", url="https://e.example/")],
    )


def itinerary(
    carrier: str = "Gulf Air", amount: float = 950, status="verified"
) -> dict:
    side = {"carrier": carrier, "duration_minutes": 80, "segments": []}
    return {
        "ignav_id": f"id-{carrier}-{amount}",
        "price": {"amount": amount, "currency": "SAR", "status": status},
        "outbound": side,
        "inbound": side,
    }


def links(url: str = "https://www.gulfair.com/book?x=1") -> dict:
    return {
        "booking_options": [
            {
                "legs": ["outbound", "inbound"],
                "links": [
                    {
                        "provider_name": "Gulf Air",
                        "url": url,
                        "specificity": "exact_flight",
                    }
                ],
            }
        ]
    }


class FakeIgnav:
    def __init__(self, body=None, link_body=None, error=False) -> None:
        self.body = {"itineraries": [itinerary()]} if body is None else body
        self.link_body = link_body or links()
        self.error = error
        self.searches: list[FlightQuery] = []
        self.link_requests = 0

    async def search(self, query: FlightQuery) -> dict:
        self.searches.append(query)
        if self.error:
            raise IgnavError("http_503")
        return self.body

    async def booking_links(self, ignav_id: str) -> dict:
        self.link_requests += 1
        return self.link_body


def make_settings(tmp_path: Path, **values) -> Settings:
    # Fake amounts here are per person, so these tests do not divide by the party.
    values.setdefault("ignav_price_scope", "per_person")
    return Settings(
        _env_file=None,
        flight_usage_db=tmp_path / "usage.sqlite3",
        **values,
    )


def checker(tmp_path: Path, fake: FakeIgnav, **values) -> FlightChecker:
    settings = make_settings(tmp_path, **values)
    return FlightChecker(settings, fake, FlightUsage(settings.flight_usage_db))


def book(check: FlightChecker, adults=2, leg_name="round_trip", member="m1", item=None):
    return asyncio.run(
        book_flight(check, item or proposal(), "الرياض", leg_name, adults, TRIP, member)
    )


def test_found_flight_returns_a_fresh_link_and_searches_for_everyone(tmp_path) -> None:
    fake = FakeIgnav()

    result = book(checker(tmp_path, fake), adults=3)

    assert result.fallback is None
    assert result.url == "https://www.gulfair.com/book?x=1"
    assert result.exact_flight
    assert fake.searches[0].adults == 3
    assert (fake.searches[0].origin_airport, fake.searches[0].destination_airport) == (
        "RUH",
        "BAH",
    )


def test_changed_price_returns_the_new_and_old_price(tmp_path) -> None:
    result = book(checker(tmp_path, FakeIgnav()))

    assert result.price_sar == Decimal("950.00")
    assert result.previous_price_sar == Decimal("900.00")


def test_same_price_reports_no_change(tmp_path) -> None:
    fake = FakeIgnav({"itineraries": [itinerary(amount=900)]})

    assert book(checker(tmp_path, fake)).previous_price_sar is None


def test_no_flight_and_no_replacement_falls_back_to_google_flights(tmp_path) -> None:
    result = book(checker(tmp_path, FakeIgnav({"itineraries": []})))

    assert result.fallback == "not_available"
    assert result.url.startswith("https://www.google.com/travel/flights")
    assert "RUH" in result.url and "BAH" in result.url
    assert "2%20adults" in result.url
    assert "Gulf%20Air" in result.url
    assert result.price_sar is None


def test_a_failed_source_never_says_the_flight_is_gone(tmp_path) -> None:
    result = book(checker(tmp_path, FakeIgnav(error=True)))

    assert result.fallback == "check_failed"
    assert not result.updated
    assert "google.com" in result.url


def test_gone_flight_moves_to_the_best_replacement(tmp_path) -> None:
    other = itinerary("Saudia", amount=1000)
    fake = FakeIgnav({"itineraries": [other]}, links("https://www.saudia.com/book?x=1"))

    result = book(checker(tmp_path, fake))

    assert result.fallback is None
    assert result.alternative.reason == "gone"
    assert result.url == "https://www.saudia.com/book?x=1"
    assert result.flights.airline.value == "Saudia"
    assert result.flights.price_per_person.amount_sar == Decimal("1000.00")
    assert result.updated


def test_replacement_over_budget_is_said_plainly(tmp_path) -> None:
    fake = FakeIgnav(
        {"itineraries": [itinerary("Saudia", amount=9000)]},
        links("https://www.saudia.com/book?x=1"),
    )
    check = checker(tmp_path, fake)

    result = asyncio.run(
        book_flight(
            check, proposal(), "الرياض", "round_trip", 1, TRIP, "m", Decimal(5000)
        )
    )

    assert result.alternative.within_budget is False
    assert result.budget_status == "over_group_budget"


def test_link_price_beats_the_search_price(tmp_path) -> None:
    # The real case: the search says 900, and Gulf Air's own page says 1614.
    priced = links("https://flights.gulfair.com/falcon/deeplink?origin=RUH")
    priced["booking_options"][0]["links"][0]["price"] = {
        "amount": 1614,
        "currency": "SAR",
        "status": "verified",
    }
    fake = FakeIgnav({"itineraries": [itinerary(amount=900)]}, priced)

    result = book(checker(tmp_path, fake))

    assert result.price_sar == Decimal("1614.00")
    assert result.previous_price_sar == Decimal("900")
    assert result.flights.price_source == "seller"


def test_seller_far_above_the_search_offers_a_cheaper_airline(tmp_path) -> None:
    class Sellers(FakeIgnav):
        async def booking_links(self, ignav_id: str) -> dict:
            self.link_requests += 1
            found = links(
                "https://www.flynas.com/b"
                if "flynas" in ignav_id
                else "https://flights.gulfair.com/d"
            )
            amount = 1000 if "flynas" in ignav_id else 1614
            found["booking_options"][0]["links"][0]["price"] = {
                "amount": amount,
                "currency": "SAR",
                "status": "verified",
            }
            return found

    fake = Sellers(
        {"itineraries": [itinerary(amount=900), itinerary("flynas", amount=1000)]}
    )

    result = book(checker(tmp_path, fake))

    assert result.price_sar == Decimal("1614.00")
    assert result.alternative.reason == "cheaper"
    assert result.alternative.price_sar == Decimal("1000.00")
    assert result.alternative.url == "https://www.flynas.com/b"
    # A suggestion: the proposal keeps its own flight.
    assert result.flights.airline.value == "Gulf Air"
    assert fake.link_requests == 2


def test_flight_with_no_usable_link_stays_and_offers_another(tmp_path) -> None:
    class Sellers(FakeIgnav):
        async def booking_links(self, ignav_id: str) -> dict:
            if "Saudia" in ignav_id:
                return links("https://www.saudia.com/book?x=1")
            return links("https://book.aegeanair.com/PostHandler.axd")

    fake = Sellers(
        {"itineraries": [itinerary(amount=900), itinerary("Saudia", amount=1000)]}
    )

    result = book(checker(tmp_path, fake))

    assert result.fallback == "no_link"
    assert "google.com" in result.url
    assert result.flights.airline.value == "Gulf Air"
    assert result.alternative.reason == "no_link"
    assert result.alternative.url == "https://www.saudia.com/book?x=1"


def test_second_source_takes_over_when_the_first_fails(tmp_path) -> None:
    broken, working = FakeIgnav(error=True), FakeIgnav()
    broken.name, working.name = "first", "second"
    settings = make_settings(tmp_path)
    check = FlightChecker(settings, providers=[broken, working])

    result = book(check)

    assert result.fallback is None
    assert result.provider == "second"


def test_second_source_takes_over_at_the_first_ones_limit(tmp_path) -> None:
    first, second = FakeIgnav(), FakeIgnav()
    first.name, second.name = "first", "second"
    settings = make_settings(tmp_path, daily_requests_per_source=2)
    check = FlightChecker(settings, providers=[first, second])
    for _ in range(2):
        check.usage.record("search", "other", False, "first")

    result = book(check)

    assert first.searches == []
    assert result.provider == "second"


def test_all_sources_at_their_limit_give_the_search_link(tmp_path) -> None:
    first, second = FakeIgnav(), FakeIgnav()
    first.name, second.name = "first", "second"
    settings = make_settings(tmp_path, daily_requests_per_source=0)

    result = book(FlightChecker(settings, providers=[first, second]))

    assert result.fallback == "limit"
    assert first.searches == [] and second.searches == []


def _priced_links(url: str, amount: float, kind: str = "airline") -> dict:
    found = links(url)
    link = found["booking_options"][0]["links"][0]
    link.pop("specificity")
    link.update(
        provider_type=kind,
        price={"amount": amount, "currency": "SAR", "status": "verified"},
    )
    return found


def test_sources_are_asked_together_and_the_airline_price_wins_a_conflict(
    tmp_path,
) -> None:
    agent = FakeIgnav(
        link_body=_priced_links("https://agent.example/x", 800, "third_party")
    )
    airline = FakeIgnav(link_body=_priced_links("https://www.gulfair.com/x", 1000))
    agent.name, airline.name = "agent", "airline"
    check = FlightChecker(make_settings(tmp_path), providers=[agent, airline])

    result = book(check)

    assert result.provider == "airline"
    assert result.price_sar == Decimal("1000.00")
    assert result.seller_type == "airline"


def test_a_link_to_the_flight_itself_beats_a_results_page(tmp_path) -> None:
    results = _priced_links("https://www.gulfair.com/list", 950)
    results["booking_options"][0]["links"][0]["specificity"] = "search_results"
    exact = _priced_links("https://agent.example/exact", 950, "third_party")
    exact["booking_options"][0]["links"][0]["specificity"] = "exact_flight"
    first, second = FakeIgnav(link_body=results), FakeIgnav(link_body=exact)
    first.name, second.name = "first", "second"

    result = book(FlightChecker(make_settings(tmp_path), providers=[first, second]))

    assert result.provider == "second"
    assert result.exact_flight


def test_link_for_another_airline_is_never_returned(tmp_path) -> None:
    # A flynas page for a Gulf Air flight, the mismatch seen in the real trial.
    wrong = links("https://booking.flynas.com/#/search?origin=RUH&destination=BAH")
    fake = FakeIgnav(
        {
            "itineraries": [
                {
                    **itinerary(),
                    "outbound": {
                        "carrier": "Gulf Air",
                        "segments": [{"marketing_carrier_code": "GF"}],
                    },
                }
            ]
        },
        wrong,
    )

    result = book(checker(tmp_path, fake))

    assert result.fallback == "no_link"
    assert "flynas" not in result.url


def test_link_checks_reject_wrong_route_and_posted_forms() -> None:
    query = FlightQuery("RUH", "BAH", date(2026, 11, 20), date(2026, 11, 30))
    both = {"outbound", "inbound"}
    assert not link_matches("https://book.aegeanair.com/PostHandler.axd", both, query)
    assert not link_matches(
        "https://a.example/?origin=JED&destination=BAH", both, query
    )
    assert not link_matches(
        "https://ajet.com/b?b1=org:CDG,dst:RUH", {"outbound"}, query
    )
    assert link_matches("https://a.example/?origin=RUH&destination=BAH", both, query)
    assert seller_matches("https://www.flynas.com/x", {"XY"})
    assert not seller_matches("https://www.flynas.com/x", {"GF"})
    assert seller_matches("https://any-agent.example/x", {"GF"})


def test_stored_link_is_never_used(tmp_path) -> None:
    saved = route()
    saved = saved.model_copy(
        update={
            "legs": [
                item.model_copy(update={"booking_url": "https://old.example/expired"})
                for item in saved.legs
            ]
        }
    )

    result = book(checker(tmp_path, FakeIgnav()), item=proposal(saved))

    assert "old.example" not in result.url


def test_every_press_asks_the_source_again_with_no_local_cache(tmp_path) -> None:
    fake = FakeIgnav()
    check = checker(tmp_path, fake)

    book(check, member="m1")
    book(check, member="m2")

    assert len(fake.searches) == 2
    assert fake.link_requests == 2
    assert check.usage.spent_today() == 4


def test_member_limit_returns_google_flights_with_no_request(tmp_path) -> None:
    fake = FakeIgnav()
    check = checker(tmp_path, fake, member_flight_actions_per_hour=1)
    book(check)
    fake.searches.clear()

    result = book(check)

    assert result.fallback == "limit"
    assert "google.com" in result.url
    assert fake.searches == []
    assert book(check, member="another").fallback is None


def test_trip_limit_returns_google_flights(tmp_path) -> None:
    fake = FakeIgnav()
    check = checker(tmp_path, fake, trip_requests_per_day=0)

    result = book(check)

    assert result.fallback == "limit"
    assert fake.searches == []


def test_project_limit_covers_other_trips_too(tmp_path) -> None:
    fake = FakeIgnav()
    check = checker(tmp_path, fake, daily_requests_per_source=1)
    check.usage.record("search", "another-trip", False, "ignav")

    assert book(check).fallback == "limit"
    assert fake.searches == []


def test_usage_records_no_private_data(tmp_path) -> None:
    check = checker(tmp_path, FakeIgnav())
    book(check, member="private-member-id")

    raw = (tmp_path / "usage.sqlite3").read_bytes()

    assert b"private-member-id" not in raw


def test_demo_mode_spends_nothing(tmp_path) -> None:
    fake = FakeIgnav()

    result = book(checker(tmp_path, fake, proposals_demo_mode=True))

    assert result.fallback == "demo"
    assert fake.searches == []


def test_member_without_flights_gets_no_route(tmp_path) -> None:
    with pytest.raises(NoRoute):
        asyncio.run(
            book_flight(
                checker(tmp_path, FakeIgnav()),
                proposal(),
                "جدة",
                "round_trip",
                1,
                TRIP,
                "m",
            )
        )


def refresh(check, item=None, ceiling="5000", adults=1, city="الرياض"):
    return asyncio.run(
        refresh_flights(
            check, item or proposal(), city, adults, Decimal(ceiling), TRIP, "m1"
        )
    )


def test_refresh_saves_the_new_price_and_time(tmp_path) -> None:
    before = route()

    result = refresh(checker(tmp_path, FakeIgnav()), proposal(before))

    assert result.updated and result.fallback is None
    assert result.flights.price_per_person.amount_sar == Decimal("950.00")
    assert result.flights.price_per_person.status == "Sourced"
    assert result.flights.priced_at is not None
    assert result.flights.group_availability == "available"
    assert result.flights.origin == before.origin
    assert result.previous_price_sar == Decimal("900")
    assert result.budget_status == "within_group_budget"


def test_refresh_uses_the_time_the_source_fetched_the_fare(tmp_path) -> None:
    body = {"observed_at": "2026-11-01T19:09:48Z", "itineraries": [itinerary()]}

    result = refresh(checker(tmp_path, FakeIgnav(body)))

    assert result.flights.priced_at.isoformat() == "2026-11-01T19:09:48+00:00"


def test_unchanged_price_reports_no_difference(tmp_path) -> None:
    fake = FakeIgnav({"itineraries": [itinerary(amount=900)]})

    result = refresh(checker(tmp_path, fake))

    assert result.previous_price_sar is None
    assert result.updated


def test_refresh_saves_cabin_fare_and_bags_when_given(tmp_path) -> None:
    body = {
        "itineraries": [
            {**itinerary(), "cabin_class": "economy", "bags": {"checked": 1}}
        ]
    }
    fares = links()
    fares["booking_options"][0]["links"][0]["fare_name"] = "Light"

    fresh = refresh(checker(tmp_path, FakeIgnav(body, fares))).flights

    assert (fresh.cabin_class, fresh.fare_name) == ("economy", "Light")
    assert fresh.checked_bags == 1
    assert fresh.carry_on_bags is None


def test_refresh_over_budget_only_changes_the_status(tmp_path) -> None:
    result = refresh(checker(tmp_path, FakeIgnav()), ceiling="1000")

    assert result.budget_status == "over_group_budget"


def test_refresh_needs_a_search_and_a_price_check(tmp_path) -> None:
    fake = FakeIgnav()

    refresh(checker(tmp_path, fake))

    assert (len(fake.searches), fake.link_requests) == (1, 1)


def test_refresh_with_no_flight_and_no_replacement_keeps_the_old_price(
    tmp_path,
) -> None:
    result = refresh(checker(tmp_path, FakeIgnav({"itineraries": []})))

    assert result.fallback == "not_available"
    assert result.flights.group_availability == "not_found"
    assert result.flights.price_per_person.amount_sar == Decimal("900.00")
    assert result.budget_status is None


def test_refresh_at_the_limit_saves_nothing(tmp_path) -> None:
    result = refresh(checker(tmp_path, FakeIgnav(), daily_requests_per_source=0))

    assert result.fallback == "limit"
    assert not result.updated
    assert "google.com" in result.url


def test_refresh_of_a_split_trip_updates_each_direction(tmp_path) -> None:
    fake = FakeIgnav(
        {"itineraries": [itinerary(amount=1000)]},
        {
            "booking_options": [
                {
                    "legs": ["outbound"],
                    "links": [
                        {
                            "provider_name": "Gulf Air",
                            "url": "https://x.example/a",
                            "price": {"amount": 600, "currency": "SAR"},
                        }
                    ],
                },
                {
                    "legs": ["inbound"],
                    "links": [
                        {
                            "provider_name": "Gulf Air",
                            "url": "https://x.example/b",
                            "price": {"amount": 400, "currency": "SAR"},
                        }
                    ],
                },
            ]
        },
    )

    result = refresh(checker(tmp_path, fake), proposal(route("split")))

    assert [item.price.amount_sar for item in result.flights.legs] == [
        Decimal("600.00"),
        Decimal("400.00"),
    ]
    assert result.flights.price_per_person.status == "Estimated"


def test_ignav_prices_are_for_the_whole_party_by_default() -> None:
    assert Settings(_env_file=None).ignav_price_scope == "total"


def test_total_price_setting_divides_by_the_party(tmp_path) -> None:
    fake = FakeIgnav({"itineraries": [itinerary(amount=1800)]})

    result = book(checker(tmp_path, fake, ignav_price_scope="total"), adults=2)

    assert result.price_sar == Decimal("900.00")
    assert result.previous_price_sar is None


def test_updates_never_call_gemini_or_tavily(tmp_path, monkeypatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("The light update must not use Gemini or Tavily.")

    monkeypatch.setattr(trip_research, "call_gemini", forbidden)
    monkeypatch.setattr(trip_research, "search_sources", forbidden)
    monkeypatch.setattr(trip_research, "extract_facts", forbidden)
    monkeypatch.setattr(trip_research, "research", forbidden)

    check = checker(tmp_path, FakeIgnav())
    assert book(check).fallback is None
    assert refresh(check).updated
    source = Path(flight_refresh.__file__).read_text(encoding="utf-8")
    assert "call_gemini" not in source and "search_sources" not in source


def provider(*responses: httpx.Response) -> tuple[IgnavProvider, list[httpx.Request]]:
    remaining = list(responses)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return remaining.pop(0)

    return IgnavProvider("k", None, httpx.MockTransport(handler)), seen


QUERY = FlightQuery("RUH", "CDG", date(2026, 11, 20), date(2026, 11, 30), 2)


def mixed(amount: float, minutes: int = 300) -> dict:
    return {
        "ignav_id": f"mixed-{amount}",
        "has_mixed_carriers": True,
        "price": {"amount": amount, "currency": "SAR", "status": "verified"},
        "outbound": {"carrier": "A", "duration_minutes": minutes, "segments": []},
        "inbound": {"carrier": "B", "duration_minutes": minutes, "segments": []},
    }


def steady(amount: float, minutes: int = 300) -> dict:
    return {
        "ignav_id": f"steady-{amount}",
        "price": {"amount": amount, "currency": "SAR", "status": "verified"},
        "outbound": {"carrier": "A", "duration_minutes": minutes, "segments": []},
        "inbound": {"carrier": "A", "duration_minutes": minutes, "segments": []},
    }


SPLIT_LINKS = {
    "booking_options": [
        {
            "legs": ["outbound"],
            "links": [
                {
                    "provider_name": "A",
                    "url": "https://a.example/o",
                    "price": {"amount": 400, "currency": "SAR"},
                }
            ],
        },
        {
            "legs": ["inbound"],
            "links": [
                {
                    "provider_name": "B",
                    "url": "https://b.example/i",
                    "price": {"amount": 300, "currency": "SAR"},
                }
            ],
        },
    ]
}
WHOLE_LINKS = {
    "booking_options": [
        {
            "legs": ["outbound", "inbound"],
            "links": [{"provider_name": "A", "url": "https://a.example/w"}],
        }
    ]
}


def test_small_saving_keeps_one_booking(tmp_path) -> None:
    ignav, seen = provider(
        httpx.Response(200, json={"itineraries": [mixed(900), steady(1000)]}),
        httpx.Response(200, json=WHOLE_LINKS),
    )

    fare = asyncio.run(ignav.find(QUERY))

    assert fare.trip_type == "round_trip"
    assert len(seen) == 2
    assert b'"adults":2' in seen[0].content.replace(b" ", b"")


def test_clear_saving_chooses_the_split_trip(tmp_path) -> None:
    ignav, seen = provider(
        httpx.Response(200, json={"itineraries": [mixed(700), steady(1000)]}),
        httpx.Response(200, json=WHOLE_LINKS),
        httpx.Response(200, json=SPLIT_LINKS),
    )

    assert asyncio.run(ignav.find(QUERY)).trip_type == "split"
    assert len(seen) == 3


def test_much_longer_split_trip_is_not_chosen(tmp_path) -> None:
    ignav, _ = provider(
        httpx.Response(200, json={"itineraries": [mixed(700, 500), steady(1000)]}),
        httpx.Response(200, json=WHOLE_LINKS),
    )

    assert asyncio.run(ignav.find(QUERY)).trip_type == "round_trip"


def test_rule_edges() -> None:
    saving, extra = Decimal("0.15"), Decimal("0.30")
    assert clearly_better(mixed(850), steady(1000), saving, extra)
    assert not clearly_better(mixed(851), steady(1000), saving, extra)
    assert clearly_better(mixed(850, 390), steady(1000), saving, extra)
    assert not clearly_better(mixed(850, 391), steady(1000), saving, extra)


def test_empty_search_for_a_group_is_remembered(tmp_path) -> None:
    ignav, _ = provider(httpx.Response(200, json={"itineraries": []}))

    assert asyncio.run(ignav.find(QUERY)) is None
    assert QUERY in ignav.no_itinerary
