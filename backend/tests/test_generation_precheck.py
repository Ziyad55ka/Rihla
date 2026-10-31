"""Precheck tests. Every outside service is fake, so these spend no quota."""

import asyncio
from datetime import date
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.generation import GenerationInput
from app.schemas.planning import GroupConflicts, PlanningStatus
from app.schemas.preferences import MemberPreferences
from app.schemas.proposals import ProposalSet
from app.services import (
    flight_prices,
    generation_precheck,
    proposal_generation,
    trip_research,
)
from app.services.generation_precheck import (
    FeasibilityReport,
    LocalProposalStore,
    build_group_conflicts,
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
    monkeypatch.setattr(generation_precheck, "call_gemini", recorder("gemini"))
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
        member(1, destinations={"value": "Secret Turkey", "importance": "Essential"}),
        member(2, destinations={"value": "Japan", "importance": "Essential"}),
    )

    blocked = blocked_by(generation, settings)

    assert blocked.categories == ["destinations"]
    assert outside_calls == []
    assert "Turkey" not in str(blocked) and "Japan" not in str(blocked)


def test_overlapping_essential_destinations_pass_stage_one(settings: Settings) -> None:
    generation = group(
        member(1, destinations={"value": "Turkey or Egypt", "importance": "Essential"}),
        member(2, destinations={"value": "egypt", "importance": "Essential"}),
    )

    generation_precheck.check_input(generation, settings)


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
    assert "749" not in str(blocked) and "150" not in str(blocked)


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
    store = LocalProposalStore(settings.generation_store_db)
    store.save(str(generation.trip_id), input_hash(generation), saved_result())

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


def fake_feasibility(
    monkeypatch: pytest.MonkeyPatch, report: FeasibilityReport
) -> list:
    payloads: list[str] = []

    async def answer(contents, system_prompt, schema, config, cost):
        payloads.append(contents)
        cost.gemini_requests += 1
        return report

    monkeypatch.setattr(generation_precheck, "call_gemini", answer)
    return payloads


def test_stage_two_stops_full_generation_with_general_categories(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    payloads = fake_feasibility(
        monkeypatch,
        FeasibilityReport(feasible=False, blocking_categories=["flights", "budget"]),
    )

    async def fail(*args, **kwargs):
        raise AssertionError("Generation must not start")

    monkeypatch.setattr(generation_precheck, "generate_proposals", fail)
    generation = group(
        member(1, flights={"value": "Secret direct", "importance": "Essential"}),
        member(2, departure_city="Jeddah", max_budget_sar="3000"),
    )

    blocked = blocked_by(generation, settings)

    assert blocked.categories == ["flights", "budget"]
    assert len(blocked.messages) == 2
    assert "Secret" not in str(blocked) and "3000" not in str(blocked)
    # The request carries group data only.
    assert "Member" not in payloads[0] and "Jeddah" not in payloads[0]
    assert "4000" not in payloads[0] and "3000" in payloads[0]


def test_stage_two_with_no_category_still_gives_a_general_message(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_feasibility(
        monkeypatch, FeasibilityReport(feasible=False, blocking_categories=[])
    )

    blocked = blocked_by(group(), settings)

    assert blocked.messages == ["The group's requirements cannot be met together."]


def test_passing_checks_generate_and_save_then_reuse(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_feasibility(
        monkeypatch, FeasibilityReport(feasible=True, blocking_categories=[])
    )
    runs: list[int] = []

    async def generated(generation, config, version):
        runs.append(version)
        return saved_result()

    monkeypatch.setattr(generation_precheck, "generate_proposals", generated)

    first = asyncio.run(generate_checked(group(), settings))
    again = asyncio.run(generate_checked(group(), settings))

    assert first.reused is False
    assert first.cost.gemini_requests == 6
    assert again.reused is True
    assert runs == [1]


def test_partial_result_is_not_saved_for_reuse(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_feasibility(
        monkeypatch, FeasibilityReport(feasible=True, blocking_categories=[])
    )
    runs: list[int] = []

    async def generated(generation, config, version):
        runs.append(version)
        return saved_result().model_copy(update={"complete": False})

    monkeypatch.setattr(generation_precheck, "generate_proposals", generated)

    asyncio.run(generate_checked(group(), settings))
    asyncio.run(generate_checked(group(), settings))

    assert len(runs) == 2


def test_all_options_over_budget_gives_a_clear_message_without_the_figure(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_feasibility(
        monkeypatch, FeasibilityReport(feasible=True, blocking_categories=[])
    )
    costly = proposal_generation.PlannedOption(
        title="Trip",
        destination="X",
        country="X",
        arrival_airport=None,
        start_date=date(2026, 12, 13),
        end_date=date(2026, 12, 17),
        cities=[proposal_generation.PlannedCity(city="X", nights=4)],
        requirement_checks=[],
    )

    async def plan(*args, **kwargs):
        return proposal_generation.TripPlan(
            options=[costly.model_copy(update={"destination": f"Place {next(names)}"})]
        )

    names = iter(range(100))

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


def own(
    importance: str = "Essential", value: str = "Secret Turkey"
) -> MemberPreferences:
    return MemberPreferences(destinations={"value": value, "importance": importance})


def conflicting_group() -> GenerationInput:
    return group(
        member(1, destinations={"value": "Secret Turkey", "importance": "Essential"}),
        member(2, destinations={"value": "Hidden Japan", "importance": "Essential"}),
    )


def test_clear_group_can_generate(settings: Settings) -> None:
    report = build_group_conflicts(planning(), group(), own(), settings)

    assert report == GroupConflicts(conflicts=[], own_review=[], can_generate=True)


def test_member_with_essential_gets_the_review_notice(settings: Settings) -> None:
    report = build_group_conflicts(planning(), conflicting_group(), own(), settings)

    assert report.conflicts == ["destinations"]
    assert report.own_review == ["destinations"]
    assert report.can_generate is False


@pytest.mark.parametrize(
    "preferences",
    [None, own(importance="Flexible"), own(value="")],
)
def test_other_members_see_the_conflict_without_the_notice(
    settings: Settings, preferences: MemberPreferences | None
) -> None:
    report = build_group_conflicts(
        planning(), conflicting_group(), preferences, settings
    )

    assert report.conflicts == ["destinations"]
    assert report.own_review == []
    assert report.can_generate is False


def test_report_never_holds_who_or_which_value(settings: Settings) -> None:
    generation = group(
        member(
            1,
            max_budget_sar="749",
            departure_city="Jeddah",
            destinations={"value": "Secret Turkey", "importance": "Essential"},
        ),
        member(2, destinations={"value": "Hidden Japan", "importance": "Essential"}),
    )

    report = build_group_conflicts(planning(), generation, own(), settings)
    body = report.model_dump_json()

    assert report.conflicts == ["destinations", "budget"]
    assert report.own_review == ["destinations"]
    for private in ("Secret", "Hidden", "Turkey", "Japan", "749", "Member", "Jeddah"):
        assert private not in body


def test_budget_conflict_gives_no_one_a_review_notice(settings: Settings) -> None:
    generation = group(member(1, max_budget_sar="749"), member(2))

    report = build_group_conflicts(planning(), generation, own(), settings)

    assert report.conflicts == ["budget"]
    assert report.own_review == []


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (planning(ready=False), ["readiness"]),
        (planning(dates="conflict"), ["dates"]),
        (planning(ready=False, dates="pending"), ["readiness", "dates"]),
        (planning(), ["readiness"]),
    ],
)
def test_no_generation_input_keeps_generation_blocked(
    settings: Settings, status: PlanningStatus, expected: list[str]
) -> None:
    report = build_group_conflicts(status, None, own(), settings)

    assert report.conflicts == expected
    assert report.can_generate is False


def test_building_the_report_makes_no_outside_calls(
    settings: Settings, outside_calls: list[str]
) -> None:
    build_group_conflicts(planning(), conflicting_group(), own(), settings)

    assert outside_calls == []


def test_can_generate_cannot_contradict_the_conflicts() -> None:
    with pytest.raises(ValidationError):
        GroupConflicts(conflicts=["dates"], own_review=[], can_generate=True)


def test_page_and_generation_use_the_same_rules(settings: Settings) -> None:
    generation = conflicting_group()

    report = build_group_conflicts(planning(), generation, None, settings)
    blocked = blocked_by(generation, settings, planning=planning())

    assert blocked.categories == report.conflicts
