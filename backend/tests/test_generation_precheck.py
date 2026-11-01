"""Precheck tests. Every outside service is fake, so these spend no quota."""

import asyncio
from datetime import date
from pathlib import Path
from uuid import UUID

import pytest

from app.core.config import Settings
from app.schemas.generation import GenerationInput
from app.schemas.planning import PlanningStatus
from app.schemas.proposals import ProposalSet
from app.services import (
    flight_prices,
    generation_precheck,
    proposal_generation,
    trip_research,
)
from app.services.generation_precheck import (
    LocalProposalStore,
    generate_checked,
    input_hash,
)
from app.services.proposal_generation import GenerationBlocked, GenerationResult
from app.services.trip_research import ResearchCost

DEMO = Settings(_env_file=None).proposals_demo_file


def member(number: int, **extra) -> dict:
    return {
        "label": f"Member {number}",
        "departure_city": "Riyadh",
        "max_budget_sar": "4000",
        **extra,
    }


def group(*members: dict) -> GenerationInput:
    return GenerationInput(
        trip_id=UUID("00000000-0000-4000-8000-0000000000aa"),
        shared_start=date(2026, 12, 13),
        shared_end=date(2026, 12, 17),
        members=list(members) or [member(1), member(2)],
    )


def planning(ready: bool = True, dates: str = "available") -> PlanningStatus:
    available = dates == "available"
    return PlanningStatus(
        all_members_ready=ready,
        own_readiness={
            "status": "Ready",
            "missing_fields": [],
            "has_saved_preferences": True,
        },
        member_readiness=None,
        member_dates=[],
        shared_dates={
            "status": dates,
            "start": date(2026, 12, 13) if available else None,
            "end": date(2026, 12, 17) if available else None,
            "duration_days": 5 if available else None,
        },
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        gemini_api_key="fake",
        tavily_api_key="fake",
        ignav_api_key="fake",
        generation_store_db=tmp_path / "store.sqlite3",
        search_cache_db=tmp_path / "cache.sqlite3",
    )


@pytest.fixture
def outside_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record any attempt to reach Gemini, Tavily or Ignav."""
    calls: list[str] = []

    def recorder(name: str):
        async def record(*args, **kwargs):
            calls.append(name)
            raise AssertionError(f"{name} must not be called")

        return record

    def client(**kwargs):
        calls.append("gemini_client")
        raise AssertionError("Gemini must not be called")

    monkeypatch.setattr(trip_research.genai, "Client", client)
    monkeypatch.setattr(trip_research, "call_gemini", recorder("gemini"))
    monkeypatch.setattr(proposal_generation, "call_gemini", recorder("gemini"))
    monkeypatch.setattr(trip_research, "search_sources", recorder("tavily"))
    monkeypatch.setattr(trip_research, "research", recorder("research"))
    monkeypatch.setattr(flight_prices.IgnavProvider, "_post", recorder("ignav"))
    return calls


def blocked_by(generation, settings, **kwargs) -> GenerationBlocked:
    with pytest.raises(GenerationBlocked) as caught:
        asyncio.run(generate_checked(generation, settings, **kwargs))
    return caught.value


@pytest.mark.parametrize(
    ("status", "category"),
    [
        (planning(ready=False), "readiness"),
        (planning(dates="conflict"), "dates"),
        (planning(dates="pending"), "dates"),
    ],
)
def test_stage_one_stops_when_not_ready_or_no_shared_dates(
    settings: Settings, outside_calls: list[str], status, category: str
) -> None:
    blocked = blocked_by(group(), settings, planning=status)

    assert blocked.categories == [category]
    assert outside_calls == []


def test_stage_one_stops_on_conflicting_essential_destinations(
    settings: Settings, outside_calls: list[str]
) -> None:
    generation = group(
        member(1, destinations={"value": "Turkey", "importance": "Essential"}),
        member(2, destinations={"value": "Japan", "importance": "Essential"}),
    )

    blocked = blocked_by(generation, settings)

    assert blocked.categories == ["destinations"]
    assert outside_calls == []
    assert "Turkey" not in str(blocked) and "Japan" not in str(blocked)


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("Turkey or Egypt", "egypt"),
        ("Turkey", "تركيا"),
        ("Istanbul", "Turkey"),
        ("Somewhere warm", "Japan"),
        ("إسطنبول", "Japan"),
    ],
)
def test_overlapping_or_doubtful_destinations_pass_stage_one(
    settings: Settings, first: str, second: str
) -> None:
    generation = group(
        member(1, destinations={"value": first, "importance": "Essential"}),
        member(2, destinations={"value": second, "importance": "Essential"}),
    )

    assert generation_precheck.find_input_conflicts(generation, settings) == []


def test_clearly_different_countries_in_arabic_are_a_conflict(
    settings: Settings,
) -> None:
    generation = group(
        member(1, destinations={"value": "مصر أو تركيا", "importance": "Essential"}),
        member(2, destinations={"value": "اليابان", "importance": "Essential"}),
    )

    assert generation_precheck.find_input_conflicts(generation, settings) == [
        "destinations"
    ]


def test_flexible_destinations_never_conflict(settings: Settings) -> None:
    generation = group(
        member(1, destinations={"value": "Turkey", "importance": "Flexible"}),
        member(2, destinations={"value": "Japan", "importance": "Essential"}),
    )

    generation_precheck.check_input(generation, settings)


def test_stage_one_stops_when_budget_is_below_the_daily_minimum(
    settings: Settings, outside_calls: list[str]
) -> None:
    generation = group(member(1, max_budget_sar="749"), member(2))

    blocked = blocked_by(generation, settings)

    assert blocked.categories == ["budget"]
    assert outside_calls == []
    assert "749" not in str(blocked) and "250" not in str(blocked)


def test_daily_minimum_comes_from_settings(settings: Settings) -> None:
    raised = settings.model_copy(update={"min_budget_sar_per_day": 1000})

    with pytest.raises(GenerationBlocked):
        generation_precheck.check_input(group(), raised)
    generation_precheck.check_input(group(), settings)


def saved_result() -> GenerationResult:
    proposals = ProposalSet.model_validate_json(DEMO.read_text(encoding="utf-8"))
    return GenerationResult(
        proposals=proposals.proposals,
        complete=True,
        message=None,
        failures=[],
        cost=ResearchCost(gemini_requests=5),
    )


def test_unchanged_inputs_return_saved_proposals_with_no_calls(
    settings: Settings, outside_calls: list[str]
) -> None:
    generation = group()
    store = LocalProposalStore(settings.generation_store_db, 3600)
    asyncio.run(
        store.save(str(generation.trip_id), input_hash(generation), saved_result())
    )

    result = asyncio.run(generate_checked(generation, settings))

    assert result.reused is True
    assert len(result.proposals) == 3
    assert result.cost == ResearchCost()
    assert outside_calls == []


def test_hash_ignores_member_order_and_labels() -> None:
    first = group(member(1, departure_city="Jeddah"), member(2))
    second = group(member(1), member(2, departure_city="Jeddah"))

    assert input_hash(first) == input_hash(second)


@pytest.mark.parametrize(
    "changed",
    [
        member(2, max_budget_sar="4001"),
        member(2, departure_city="Jeddah"),
        member(2, interests={"value": "Museums", "importance": "Flexible"}),
    ],
)
def test_any_changed_input_changes_the_hash(changed: dict) -> None:
    assert input_hash(group(member(1), member(2))) != input_hash(
        group(member(1), changed)
    )


def plan_answer(monkeypatch: pytest.MonkeyPatch, plan) -> list[str]:
    payloads: list[str] = []

    async def answer(contents, system_prompt, schema, config, cost):
        payloads.append(contents)
        cost.gemini_requests += 1
        return plan

    monkeypatch.setattr(proposal_generation, "call_gemini", answer)
    return payloads


def impossible(*categories: str) -> proposal_generation.TripPlan:
    return proposal_generation.TripPlan(
        feasible=False, blocking_categories=list(categories), options=[]
    )


def test_impossible_answer_stops_before_any_search_in_one_request(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    payloads = plan_answer(monkeypatch, impossible("flights", "budget"))

    async def fail(*args, **kwargs):
        raise AssertionError("Research must not start")

    monkeypatch.setattr(trip_research, "research", fail)
    generation = group(
        member(1, flights={"value": "Secret direct", "importance": "Essential"}),
        member(2, departure_city="Jeddah", max_budget_sar="3000"),
    )

    blocked = blocked_by(generation, settings)

    assert len(payloads) == 1
    assert blocked.categories == ["flights", "budget"]
    assert len(blocked.messages) == 2
    assert "Secret" not in str(blocked) and "3000" not in str(blocked)
    assert "Member" not in payloads[0] and "Jeddah" not in payloads[0]


def test_impossible_with_no_category_still_gives_a_general_message(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_answer(monkeypatch, impossible())

    blocked = blocked_by(group(), settings)

    assert blocked.messages == ["The group's requirements cannot be met together."]


def test_impossible_retry_gives_no_option_and_does_not_block(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    payloads = plan_answer(monkeypatch, impossible("budget"))
    used: set = set()

    options = asyncio.run(
        proposal_generation._plan_options(
            1,
            group(),
            [],
            used,
            settings,
            ResearchCost(),
        )
    )

    assert options == []
    assert len(payloads) == 1


def counted_generation(monkeypatch: pytest.MonkeyPatch, result=None) -> list[int]:
    runs: list[int] = []

    async def generated(generation, config, version):
        runs.append(version)
        return result or saved_result()

    monkeypatch.setattr(generation_precheck, "generate_proposals", generated)
    return runs


def test_passing_checks_generate_and_save_then_reuse(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs = counted_generation(monkeypatch)

    first = asyncio.run(generate_checked(group(), settings))
    again = asyncio.run(generate_checked(group(), settings))

    assert first.reused is False
    assert first.cost.gemini_requests == 5
    assert again.reused is True
    assert runs == [1]


def test_saved_proposals_expire_after_the_time_limit(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs = counted_generation(monkeypatch)
    asyncio.run(generate_checked(group(), settings))

    now = generation_precheck.time.time()
    monkeypatch.setattr(generation_precheck.time, "time", lambda: now + 23 * 3600)
    assert asyncio.run(generate_checked(group(), settings)).reused is True

    monkeypatch.setattr(generation_precheck.time, "time", lambda: now + 24 * 3600)
    assert asyncio.run(generate_checked(group(), settings)).reused is False
    assert len(runs) == 2


def test_regenerate_skips_saved_proposals_and_replaces_them(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs = counted_generation(monkeypatch)
    asyncio.run(generate_checked(group(), settings))

    fresh = asyncio.run(generate_checked(group(), settings, regenerate=True))
    again = asyncio.run(generate_checked(group(), settings))

    assert fresh.reused is False
    assert again.reused is True
    assert len(runs) == 2


def test_regenerate_still_runs_stage_one(
    settings: Settings, outside_calls: list[str]
) -> None:
    generation = group(member(1, max_budget_sar="749"), member(2))

    blocked = blocked_by(generation, settings, regenerate=True)

    assert blocked.categories == ["budget"]
    assert outside_calls == []


def test_partial_result_is_not_saved_for_reuse(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs = counted_generation(
        monkeypatch, saved_result().model_copy(update={"complete": False})
    )

    asyncio.run(generate_checked(group(), settings))
    asyncio.run(generate_checked(group(), settings))

    assert len(runs) == 2


def test_all_options_over_budget_gives_a_clear_message_without_the_figure(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    names = iter(range(100))

    async def plan(*args, **kwargs):
        place = f"Place {next(names)}"
        option = proposal_generation.PlannedOption(
            title="Trip",
            destination=place,
            country="X",
            arrival_airport=None,
            start_date=date(2026, 12, 13),
            end_date=date(2026, 12, 17),
            cities=[proposal_generation.PlannedCity(city=place, nights=4)],
            requirement_checks=[],
        )
        return proposal_generation.TripPlan(
            feasible=True, blocking_categories=[], options=[option]
        )

    async def rejected(*args, **kwargs):
        raise proposal_generation.OptionRejected("over_group_budget")

    monkeypatch.setattr(proposal_generation, "call_gemini", plan)
    monkeypatch.setattr(proposal_generation, "_complete_option", rejected)

    blocked = blocked_by(group(), settings)

    assert blocked.categories == ["budget"]
    assert "4000" not in str(blocked)


def test_demo_mode_skips_the_checks(
    settings: Settings, outside_calls: list[str]
) -> None:
    demo = settings.model_copy(update={"proposals_demo_mode": True})

    result = asyncio.run(generate_checked(group(member(1, max_budget_sar="1")), demo))

    assert result.demo is True
    assert outside_calls == []


def test_default_daily_minimum_is_250_per_trip_day(settings: Settings) -> None:
    just_under = group(member(1, max_budget_sar="1249.99"), member(2))
    exactly = group(member(1, max_budget_sar="1250"), member(2))

    assert generation_precheck.find_input_conflicts(just_under, settings) == ["budget"]
    assert generation_precheck.find_input_conflicts(exactly, settings) == []


def test_hash_changes_with_the_key_so_it_cannot_be_recomputed() -> None:
    assert input_hash(group(), "first-key") != input_hash(group(), "second-key")
    assert input_hash(group(), "first-key") == input_hash(group(), "first-key")


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("فرنسا، البحرين", "البحرين"),
        ("France, Bahrain", "bahrain"),
        ("فرنسا، البحرين", "Bahrain, Japan"),
    ],
)
def test_several_destinations_are_alternatives_not_a_conflict(
    settings: Settings, first: str, second: str
) -> None:
    generation = group(
        member(1, destinations={"value": first, "importance": "Essential"}),
        member(2, destinations={"value": second, "importance": "Essential"}),
    )

    assert generation_precheck.find_input_conflicts(generation, settings) == []


def test_alternatives_with_no_shared_country_are_a_conflict(settings: Settings) -> None:
    generation = group(
        member(1, destinations={"value": "فرنسا، البحرين", "importance": "Essential"}),
        member(2, destinations={"value": "اليابان", "importance": "Essential"}),
    )

    assert generation_precheck.find_input_conflicts(generation, settings) == [
        "destinations"
    ]


def test_planner_is_told_destinations_are_alternatives() -> None:
    assert "alternatives" in proposal_generation.PLANNER_PROMPT
