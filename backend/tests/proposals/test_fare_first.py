"""Fare-first generation. Gemini, Tavily and Ignav are fake: no quota is spent."""

import asyncio
import time
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from app.core.config import Settings
from app.schemas.generation import GenerationInput
from app.services import fare_first, flight_prices, proposal_generation, trip_research
from app.services.flight_prices import FareLeg, FlightFare, FlightQuery
from app.services.generation_errors import GenerationNeedsChanges
from app.services.generation_progress import ProgressReporter, read_progress
from app.services.proposal_generation import (
    GenerationBlocked,
    OptionRejected,
    PlannedCity,
    PlannedOption,
    TripPlan,
)
from app.services.trip_research import ResearchError
from tests.proposals.test_proposal_generation import fake_research

TODAY = date(2026, 11, 3)
TRIP = UUID("00000000-0000-4000-8000-0000000000bb")


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fare_first, "today", lambda: TODAY)


def settings(tmp_path: Path, **extra) -> Settings:
    values = {
        "gemini_api_key": "fake",
        "tavily_api_key": "fake",
        "ignav_api_key": "fake",
        "gemini_retry_delay_seconds": 0,
        "search_cache_db": tmp_path / "cache.sqlite3",
    }
    return Settings(_env_file=None, **{**values, **extra})


def group(start=date(2026, 11, 20), end=date(2026, 11, 26)) -> GenerationInput:
    return GenerationInput(
        trip_id=TRIP,
        shared_start=start,
        shared_end=end,
        members=[
            {"label": "Member 1", "departure_city": "Riyadh", "max_budget_sar": "9000"},
            {"label": "Member 2", "departure_city": "Riyadh", "max_budget_sar": "9000"},
            {"label": "Member 3", "departure_city": "Jeddah", "max_budget_sar": "9000"},
        ],
    )


def option(place: str, airport: str, start=date(2026, 11, 20), nights=4):
    return PlannedOption(
        title=f"Trip to {place}",
        title_ar=None,
        title_en=None,
        destination_ar=None,
        cities_ar=None,
        destination=place,
        country=place,
        arrival_airport=airport,
        start_date=start,
        end_date=date.fromordinal(start.toordinal() + nights),
        cities=[PlannedCity(city=place, nights=nights)],
        requirement_checks=[],
    )


def fare() -> FlightFare:
    leg = FareLeg(
        "outbound", "2026-11-20", "Saudia", 120, "900", "SAR", "https://x.example/b"
    )
    return FlightFare("Saudia", 240, "900", "SAR", True, "Saudia", "round_trip", (leg,))


def planner(*batches: list[PlannedOption]):
    """Each Gemini request returns the next batch of options."""
    queue = list(batches)
    asked: list[dict] = []

    async def call(payload, prompt, schema, config, cost):
        import json

        cost.gemini_requests += 1
        asked.append(json.loads(payload))
        options = queue.pop(0) if queue else []
        return TripPlan(feasible=True, blocking_categories=[], options=options)

    return call, asked


def flights(available: dict[str, set[date] | None]):
    """available: airport -> departure dates with flights (None = every date)."""
    calls: list[FlightQuery] = []

    async def find(self, query: FlightQuery):
        calls.append(query)
        days = available.get(query.destination_airport, set())
        if days is None or query.departure_date in days:
            return fare()
        return None

    return find, calls


def run(generation, config, progress=None):
    return asyncio.run(
        proposal_generation.generate_proposals(generation, config, 1, progress=progress)
    )


def test_keeps_only_destinations_with_flights_and_never_researches_the_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    call, _ = planner(
        [
            option("Doha", "DOH"),
            option("Nowhere", "NWH"),
            option("Paris", "CDG"),
            option("Istanbul", "IST"),
            option("Cairo", "CAI"),
        ]
    )
    find, _ = flights({"DOH": None, "CDG": None, "IST": None, "CAI": None})
    researched: list[str] = []
    base = fake_research()

    async def research(request, config):
        researched.append(request.destination)
        assert request.require_live_fares is True
        return await base(request, config)

    monkeypatch.setattr(proposal_generation, "call_gemini", call)
    monkeypatch.setattr(flight_prices.IgnavProvider, "find", find)
    monkeypatch.setattr(trip_research, "research", research)

    result = run(group(), settings(tmp_path))

    assert [p.destination for p in result.proposals] == ["Doha", "Paris", "Istanbul"]
    assert [p.option_number for p in result.proposals] == [1, 2, 3]
    assert "Nowhere" not in researched and "Cairo" not in researched
    assert result.complete is True
    assert result.cost.gemini_requests == 1


def test_one_search_per_departure_airport_with_everyone_from_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    call, _ = planner([option("Doha", "DOH")])
    find, calls = flights({"DOH": None})
    monkeypatch.setattr(proposal_generation, "call_gemini", call)
    monkeypatch.setattr(flight_prices.IgnavProvider, "find", find)
    monkeypatch.setattr(trip_research, "research", fake_research())

    run(group(), settings(tmp_path, max_gemini_calls_per_generation=1))

    assert {(q.origin_airport, q.adults) for q in calls} == {("RUH", 2), ("JED", 1)}


def test_moves_the_departure_a_day_when_the_planned_day_has_no_flights(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    call, _ = planner([option("Doha", "DOH")])
    find, _ = flights({"DOH": {date(2026, 11, 21)}})
    monkeypatch.setattr(proposal_generation, "call_gemini", call)
    monkeypatch.setattr(flight_prices.IgnavProvider, "find", find)
    monkeypatch.setattr(trip_research, "research", fake_research())
    progress = ProgressReporter(str(TRIP))

    result = run(
        group(), settings(tmp_path, max_gemini_calls_per_generation=1), progress
    )

    proposal = result.proposals[0]
    assert (proposal.start_date, proposal.end_date) == (
        date(2026, 11, 21),
        date(2026, 11, 25),
    )
    state = read_progress(str(TRIP))
    assert state is not None and state.options[0].status == "ready"
    assert state.options[0].date_shift_days == 1


def test_never_departs_sooner_than_the_lead_days(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The group's dates start today; flights exist every day.
    call, _ = planner([option("Doha", "DOH", start=TODAY, nights=4)])
    find, calls = flights({"DOH": None})
    monkeypatch.setattr(proposal_generation, "call_gemini", call)
    monkeypatch.setattr(flight_prices.IgnavProvider, "find", find)
    monkeypatch.setattr(trip_research, "research", fake_research())

    result = run(
        group(start=TODAY, end=date(2026, 11, 15)),
        settings(tmp_path, max_gemini_calls_per_generation=1),
    )

    assert result.proposals[0].start_date == date(2026, 11, 6)
    assert min(q.departure_date for q in calls) >= date(2026, 11, 6)


def test_no_flights_anywhere_explains_and_suggests_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    call, asked = planner([option("Doha", "DOH")], [option("Paris", "CDG")])
    find, _ = flights({})
    monkeypatch.setattr(proposal_generation, "call_gemini", call)
    monkeypatch.setattr(flight_prices.IgnavProvider, "find", find)
    monkeypatch.setattr(trip_research, "research", fake_research())

    with pytest.raises(GenerationNeedsChanges) as caught:
        run(group(start=date(2026, 11, 20), end=date(2026, 11, 24)), settings(tmp_path))

    error = caught.value
    assert error.code == "no_flights"
    assert "Doha" in error.message and "Paris" in error.message
    actions = [item.action for item in error.suggestions]
    assert actions[0] == "edit_dates"  # the dates leave no room to move
    assert "edit_preferences" in actions and "retry" in actions
    # The second request told Gemini why, and which routes to avoid.
    assert asked[1]["previous_problem"] == "no_flights"
    assert {"destination": "doha", "cities": ["doha"]} in asked[1]["avoid_routes"]
    detail = error.detail()
    assert "9000" not in str(detail) and "Riyadh" not in str(detail)


def test_research_that_loses_the_fare_drops_the_option_not_the_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    call, _ = planner([option("Doha", "DOH"), option("Paris", "CDG")])
    find, _ = flights({"DOH": None, "CDG": None})
    base = fake_research()

    async def research(request, config):
        if request.destination == "Paris":
            raise ResearchError("no_flights", "gone")
        return await base(request, config)

    monkeypatch.setattr(proposal_generation, "call_gemini", call)
    monkeypatch.setattr(flight_prices.IgnavProvider, "find", find)
    monkeypatch.setattr(trip_research, "research", research)

    result = run(group(), settings(tmp_path, max_gemini_calls_per_generation=1))

    assert [p.destination for p in result.proposals] == ["Doha"]
    assert result.complete is False
    assert "bookable flights" in (result.message or "")


def test_every_option_over_budget_is_reported_as_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    call, _ = planner([option("Doha", "DOH")])
    find, _ = flights({"DOH": None})

    async def research(*args, **kwargs):
        raise OptionRejected("over_group_budget")

    monkeypatch.setattr(proposal_generation, "call_gemini", call)
    monkeypatch.setattr(flight_prices.IgnavProvider, "find", find)
    monkeypatch.setattr(fare_first, "_research_option", research)

    with pytest.raises(GenerationBlocked) as caught:
        run(group(), settings(tmp_path, max_gemini_calls_per_generation=1))
    assert caught.value.categories == ["budget"]


def test_research_runs_options_at_the_same_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    call, _ = planner(
        [option("Doha", "DOH"), option("Paris", "CDG"), option("Rome", "FCO")]
    )
    find, _ = flights({"DOH": None, "CDG": None, "FCO": None})
    base = fake_research()

    async def slow(request, config):
        await asyncio.sleep(0.2)
        return await base(request, config)

    monkeypatch.setattr(proposal_generation, "call_gemini", call)
    monkeypatch.setattr(flight_prices.IgnavProvider, "find", find)
    monkeypatch.setattr(trip_research, "research", slow)

    started = time.perf_counter()
    result = run(group(), settings(tmp_path))
    assert len(result.proposals) == 3
    assert time.perf_counter() - started < 0.5  # not 3 x 0.2 s


def test_without_an_ignav_key_the_web_flow_is_unchanged(tmp_path: Path) -> None:
    assert fare_first.live_fares_on(settings(tmp_path, ignav_api_key=None)) is False
    assert fare_first.live_fares_on(settings(tmp_path)) is True


def test_hotel_price_reaches_progress_without_private_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    call, _ = planner([option("Doha", "DOH")])
    find, _ = flights({"DOH": None})
    monkeypatch.setattr(proposal_generation, "call_gemini", call)
    monkeypatch.setattr(flight_prices.IgnavProvider, "find", find)
    monkeypatch.setattr(trip_research, "research", fake_research(night="420"))
    progress = ProgressReporter(str(TRIP))

    run(group(), settings(tmp_path, max_gemini_calls_per_generation=1), progress)

    state = read_progress(str(TRIP))
    assert state is not None
    assert state.options[0].hotel_price_per_night_sar == Decimal("420.00")
    dumped = state.model_dump_json()
    assert "9000" not in dumped and "Riyadh" not in dumped and "Jeddah" not in dumped
