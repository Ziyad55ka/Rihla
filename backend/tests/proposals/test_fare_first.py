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
from tests.proposals.test_proposal_generation import fake_research as web_research
from tests.proposals.test_proposal_generation import field

TODAY = date(2026, 11, 3)
TRIP = UUID("00000000-0000-4000-8000-0000000000bb")


def fake_research(night="200"):
    base = web_research(night=night)

    async def researched(request, config):
        result = await base(request, config)
        for index, origin in enumerate(request.origins):
            query = FlightQuery(
                flight_prices.airport_for_city(origin),
                request.arrival_airport,
                request.departure_date,
                request.return_date,
            )
            result.fares[index] = fare(query)
            result.airports[index] = (query.origin_airport, query.destination_airport)
        for index in range(len(request.cities) - 1):
            result.fields.extend(
                [
                    field(f"intercity.{index}.mode", "Bus"),
                    field(f"intercity.{index}.duration", "3 hours"),
                    field(f"intercity.{index}.price_per_person", sar="40"),
                ]
            )
        return result

    return researched


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


def test_price_above_lowest_member_budget_stops_before_hotel_research(
    tmp_path, monkeypatch
):
    from dataclasses import replace

    call, _ = planner([option("Paris", "CDG")], [])

    async def expensive(self, query):
        return replace(fare(query), amount="9500")

    async def should_not_research(*args, **kwargs):
        raise AssertionError("Unneeded hotel/model research")

    monkeypatch.setattr(proposal_generation, "call_gemini", call)
    monkeypatch.setattr(flight_prices.IgnavProvider, "find", expensive)
    monkeypatch.setattr(trip_research, "research", should_not_research)
    with pytest.raises(GenerationBlocked) as caught:
        run(group(), settings(tmp_path))
    assert caught.value.categories == ["budget"]


def test_separate_bookings_stop_before_hotel_research(tmp_path, monkeypatch):
    from dataclasses import replace

    call, _ = planner([option("Doha", "DOH")], [])

    async def split(self, query):
        return replace(fare(query), trip_type="split")

    async def should_not_research(*args, **kwargs):
        raise AssertionError("A split booking must stop before hotel/model work")

    monkeypatch.setattr(proposal_generation, "call_gemini", call)
    monkeypatch.setattr(flight_prices.IgnavProvider, "find", split)
    monkeypatch.setattr(trip_research, "research", should_not_research)
    with pytest.raises(GenerationNeedsChanges) as caught:
        run(group(), settings(tmp_path))
    assert caught.value.code == "no_flights"


def test_research_cannot_replace_a_verified_joint_ticket_with_split_bookings(
    tmp_path, monkeypatch
):
    from dataclasses import replace

    call, _ = planner([option("Doha", "DOH")], [])
    find, _ = flights({"DOH": None})
    base = fake_research()

    async def contradictory(request, config):
        result = await base(request, config)
        result.fares = {
            index: replace(value, trip_type="split")
            for index, value in result.fares.items()
        }
        return result

    monkeypatch.setattr(proposal_generation, "call_gemini", call)
    monkeypatch.setattr(flight_prices.IgnavProvider, "find", find)
    monkeypatch.setattr(trip_research, "research", contradictory)
    with pytest.raises(GenerationNeedsChanges) as caught:
        run(group(), settings(tmp_path))
    assert caught.value.code == "no_flights"


def test_past_shared_dates_stop_before_any_model_request(tmp_path, monkeypatch):
    call, asked = planner([])
    monkeypatch.setattr(proposal_generation, "call_gemini", call)
    with pytest.raises(GenerationNeedsChanges) as caught:
        run(group(start=date(2026, 10, 1), end=date(2026, 10, 5)), settings(tmp_path))
    assert caught.value.code == "dates_unavailable"
    assert asked == []


def test_one_source_failure_preserves_other_verified_options(tmp_path, monkeypatch):
    call, asked = planner(
        [option("Doha", "DOH"), option("Paris", "CDG"), option("Cairo", "CAI")]
    )

    async def find(self, query):
        if query.destination_airport == "CDG":
            raise ResearchError("flight_source_unavailable", "Temporary")
        return fare(query)

    monkeypatch.setattr(proposal_generation, "call_gemini", call)
    monkeypatch.setattr(flight_prices.IgnavProvider, "find", find)
    monkeypatch.setattr(trip_research, "research", fake_research())
    result = run(group(), settings(tmp_path))
    assert {p.destination for p in result.proposals} == {"Doha", "Cairo"}
    assert result.complete is False
    assert len(asked) == 1


def fare(query: FlightQuery) -> FlightFare:
    leg = FareLeg(
        "outbound",
        query.departure_date.isoformat(),
        "Saudia",
        120,
        "900",
        "SAR",
        "https://x.example/b",
    )
    back = FareLeg(
        "return",
        query.return_date.isoformat(),
        "Saudia",
        120,
        None,
        None,
        "https://x.example/b",
    )
    return FlightFare(
        "Saudia", 240, "900", "SAR", True, "Saudia", "round_trip", (leg, back)
    )


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
            return fare(query)
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


def test_proposals_are_ranked_by_the_least_satisfied_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.schemas.proposals import ProposalFit

    call, _ = planner(
        [option("Doha", "DOH"), option("Paris", "CDG"), option("Rome", "FCO")]
    )
    find, _ = flights({"DOH": None, "CDG": None, "FCO": None})
    fits = {"Doha": (60, 90), "Paris": (80, 85), "Rome": (80, 88)}

    def fake_fit(option, generation, requirements, status):
        least, average = fits[option.destination]
        return ProposalFit(
            group_percent=average, least_satisfied_percent=least, member_count=3
        )

    monkeypatch.setattr(proposal_generation, "call_gemini", call)
    monkeypatch.setattr(flight_prices.IgnavProvider, "find", find)
    monkeypatch.setattr(trip_research, "research", fake_research())
    monkeypatch.setattr(proposal_generation, "proposal_fit", fake_fit)

    result = run(group(), settings(tmp_path))

    assert [p.destination for p in result.proposals] == ["Rome", "Paris", "Doha"]
    assert [p.option_number for p in result.proposals] == [1, 2, 3]


def test_two_city_trip_flies_home_from_the_last_city(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trip = option("France and Spain", "CDG", nights=6).model_copy(
        update={
            "cities": [
                PlannedCity(city="Paris", nights=3),
                PlannedCity(city="Barcelona", nights=3),
            ],
            "return_airport": "BCN",
        }
    )
    call, _ = planner([trip])
    find, calls = flights({"CDG": None})
    seen: list[str | None] = []

    async def research(request, config):
        # Only what research is asked matters here, not building the proposal.
        seen.append(request.return_airport)
        raise ResearchError("stop here")

    monkeypatch.setattr(proposal_generation, "call_gemini", call)
    monkeypatch.setattr(flight_prices.IgnavProvider, "find", find)
    monkeypatch.setattr(trip_research, "research", research)

    with pytest.raises((GenerationNeedsChanges, ResearchError)):
        run(group(), settings(tmp_path, max_gemini_calls_per_generation=1))

    assert {q.return_from_airport for q in calls} == {"BCN"}
    assert seen == ["BCN"]


def test_one_city_or_same_airport_needs_no_separate_return() -> None:
    from app.services.proposal_generation import return_airport_of

    single = option("Paris", "CDG").model_copy(update={"return_airport": "ORY"})
    assert return_airport_of(single) is None
    same = option("Paris", "CDG").model_copy(
        update={
            "cities": [
                PlannedCity(city="Paris", nights=2),
                PlannedCity(city="Lyon", nights=2),
            ],
            "return_airport": "CDG",
        }
    )
    assert return_airport_of(same) is None


@pytest.mark.parametrize("last_nights", [None, 0, 1])
def test_same_airport_multicity_plan_needs_a_final_airport_city_stay(last_nights):
    from app.services.proposal_generation import _prevalidate

    cities = [
        PlannedCity(city="Istanbul", nights=2),
        PlannedCity(city="Bursa", nights=2),
    ]
    if last_nights is not None:
        cities[1].nights -= last_nights
        cities.append(PlannedCity(city="Istanbul", nights=last_nights))
    candidate = option("Turkey", "IST").model_copy(update={"cities": cities})
    if last_nights == 1:
        assert _prevalidate(candidate, group(), []) == []
    else:
        with pytest.raises(OptionRejected) as caught:
            _prevalidate(candidate, group(), [])
        assert "invalid_itinerary" in caught.value.reasons


def test_missing_return_transfer_stops_before_supplier_requests(tmp_path, monkeypatch):
    candidate = option("Turkey", "IST").model_copy(
        update={
            "cities": [
                PlannedCity(city="Istanbul", nights=2),
                PlannedCity(city="Bursa", nights=2),
            ]
        }
    )
    call, _ = planner([candidate], [])

    async def should_not_search(*args):
        raise AssertionError("An incomplete ground route must not spend fare requests")

    monkeypatch.setattr(proposal_generation, "call_gemini", call)
    monkeypatch.setattr(flight_prices.IgnavProvider, "find", should_not_search)
    with pytest.raises(GenerationNeedsChanges):
        run(group(), settings(tmp_path))


def test_loop_route_research_includes_both_ground_journeys(tmp_path, monkeypatch):
    candidate = option("Turkey", "IST").model_copy(
        update={
            "cities": [
                PlannedCity(city="Istanbul", nights=2),
                PlannedCity(city="Bursa", nights=1),
                PlannedCity(city="Istanbul", nights=1),
            ]
        }
    )
    call, _ = planner([candidate], [])
    find, _ = flights({"IST": None})
    monkeypatch.setattr(proposal_generation, "call_gemini", call)
    monkeypatch.setattr(flight_prices.IgnavProvider, "find", find)
    monkeypatch.setattr(trip_research, "research", fake_research())
    result = run(group(), settings(tmp_path))
    assert len(result.proposals) == 1
    proposal = result.proposals[0]
    assert [(leg.from_city, leg.to_city) for leg in proposal.intercity_transport] == [
        ("Istanbul", "Bursa"),
        ("Bursa", "Istanbul"),
    ]
    assert all(
        leg.price_per_person.amount_sar > 0 for leg in proposal.intercity_transport
    )


def test_no_flights_says_why_in_plain_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    call, _ = planner([option("Doha", "DOH")], [option("Paris", "CDG")])

    async def late_only(self, query):
        self.miss_reasons[query] = "lands_after_trip"
        return None

    monkeypatch.setattr(proposal_generation, "call_gemini", call)
    monkeypatch.setattr(flight_prices.IgnavProvider, "find", late_only)
    monkeypatch.setattr(trip_research, "research", fake_research())
    with pytest.raises(GenerationNeedsChanges) as caught:
        run(group(start=date(2026, 11, 20), end=date(2026, 11, 24)), settings(tmp_path))
    causes = caught.value.detail()["causes"]
    assert [item["kind"] for item in causes] == ["lands_after_trip"]
    assert "last day" in causes[0]["text"]


def test_dates_the_source_cannot_search_ask_for_other_dates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    call, _ = planner([option("Doha", "DOH")], [option("Paris", "CDG")])

    async def not_searchable(self, query):
        self.miss_reasons[query] = "dates_not_searchable"
        return None

    monkeypatch.setattr(proposal_generation, "call_gemini", call)
    monkeypatch.setattr(flight_prices.IgnavProvider, "find", not_searchable)
    monkeypatch.setattr(trip_research, "research", fake_research())
    with pytest.raises(GenerationNeedsChanges) as caught:
        run(group(start=date(2026, 11, 20), end=date(2026, 11, 24)), settings(tmp_path))
    causes = caught.value.detail()["causes"]
    assert causes[0]["kind"] == "dates_not_searchable"
    assert "earlier dates" in causes[0]["text"]


def test_too_dear_somewhere_is_a_price_problem_even_with_no_flights_elsewhere(
    tmp_path, monkeypatch
):
    from dataclasses import replace

    call, _ = planner([option("Paris", "CDG"), option("Nowhere", "NWH")], [])

    async def find(self, query):
        # Paris has flights but above the lowest budget; Nowhere has none.
        return (
            replace(fare(query), amount="9500")
            if query.destination_airport == "CDG"
            else None
        )

    monkeypatch.setattr(proposal_generation, "call_gemini", call)
    monkeypatch.setattr(flight_prices.IgnavProvider, "find", find)
    with pytest.raises(GenerationBlocked) as caught:
        run(group(), settings(tmp_path))
    assert caught.value.categories == ["budget"]


def test_common_ground_leads_when_members_want_different_places(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.schemas.preferences import OptionalPreference
    from app.schemas.proposals import ProposalFit
    from app.services.proposal_generation import RequirementCheck

    why = "A shared option with landmarks and food the group enjoys."

    def checks(paris: bool, madrid: bool):
        return [
            RequirementCheck(
                requirement_id="R1", met=paris, explanation=None if paris else why
            ),
            RequirementCheck(
                requirement_id="R2", met=madrid, explanation=None if madrid else why
            ),
        ]

    bridge = option("Barcelona", "BCN").model_copy(
        update={"common_ground": True, "requirement_checks": checks(False, False)}
    )
    paris = option("Paris", "CDG").model_copy(
        update={"requirement_checks": checks(True, False)}
    )
    madrid = option("Madrid", "MAD").model_copy(
        update={"requirement_checks": checks(False, True)}
    )
    call, _ = planner([paris, madrid, bridge])
    find, _ = flights({"BCN": None, "CDG": None, "MAD": None})
    fits = {"Paris": (62, 69), "Madrid": (62, 69), "Barcelona": (62, 62)}

    def fake_fit(option, generation, requirements, status):
        least, average = fits[option.destination]
        return ProposalFit(
            group_percent=average, least_satisfied_percent=least, member_count=3
        )

    monkeypatch.setattr(proposal_generation, "call_gemini", call)
    monkeypatch.setattr(flight_prices.IgnavProvider, "find", find)
    monkeypatch.setattr(trip_research, "research", fake_research())
    monkeypatch.setattr(proposal_generation, "proposal_fit", fake_fit)
    wishes = group()
    members = [
        m.model_copy(update={"destinations": OptionalPreference(value=place)})
        for m, place in zip(wishes.members, ["Paris", "Madrid", "Paris"], strict=True)
    ]

    result = run(wishes.model_copy(update={"members": members}), settings(tmp_path))

    assert [p.destination for p in result.proposals][0] == "Barcelona"
    assert [p.option_number for p in result.proposals] == [1, 2, 3]
    # Two wishes adjusted the same way read as one line.
    assert len(result.proposals[0].flexible_adjustments) == 1
