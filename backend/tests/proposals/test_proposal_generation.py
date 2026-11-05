"""Generation tests. Gemini and Tavily are fake, so these spend no quota."""

import asyncio
import json
import logging
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from google.genai import errors as genai_errors

from app.core.config import Settings
from app.schemas.generation import GenerationInput
from app.schemas.proposals import ProposalSet
from app.services import proposal_generation, trip_research
from app.services.flight_prices import FareLeg, FlightFare
from app.services.proposal_generation import (
    PlannedCity,
    PlannedOption,
    RequirementCheck,
    TripPlan,
    collect_requirements,
    contains_private_detail,
    generate_proposals,
    hotel_search_url,
)
from app.services.trip_research import (
    ResearchCost,
    ResearchError,
    ResearchResult,
    ResearchSource,
    VerifiedField,
    call_gemini,
)

EVIDENCE = [{"source_id": 1, "quote": "A cited sentence."}]
EMPTY_PLAN = '{"feasible": true, "blocking_categories": [], "options": []}'


def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        gemini_api_key="fake",
        tavily_api_key="fake",
        gemini_retry_delay_seconds=0,
        search_cache_db=tmp_path / "cache.sqlite3",
    )


def group(**first_member) -> GenerationInput:
    member = {
        "label": "Member 1",
        "departure_city": "Riyadh",
        "max_budget_sar": "5000",
    }
    return GenerationInput(
        trip_id=UUID("00000000-0000-4000-8000-0000000000aa"),
        shared_start=date(2026, 11, 20),
        shared_end=date(2026, 11, 24),
        members=[
            {**member, **first_member},
            {
                "label": "Member 2",
                "departure_city": "Jeddah",
                "max_budget_sar": "3000",
            },
        ],
    )


def option(
    destination: str,
    title: str = "A relaxed city break",
    checks: list[RequirementCheck] | None = None,
    start: date = date(2026, 11, 20),
) -> PlannedOption:
    return PlannedOption(
        title=title,
        title_ar=None,
        title_en=None,
        destination_ar=None,
        cities_ar=None,
        destination=destination,
        country=destination,
        arrival_airport=None,
        start_date=start,
        end_date=date(2026, 11, 24),
        cities=[
            PlannedCity(city=destination, nights=(date(2026, 11, 24) - start).days)
        ],
        requirement_checks=checks or [],
    )


def field(
    field_id: str, value: str | None = None, sar: str | None = None
) -> VerifiedField:
    shown = value is not None or sar is not None
    return VerifiedField(
        field_id=field_id,
        category="test",
        value=value or sar,
        status="Estimated" if shown else "Not available",
        evidence=EVIDENCE if shown else [],
        amount_sar=Decimal(sar) if sar else None,
    )


def fake_research(fare: str = "1000", night: str = "200"):
    async def research(request, config) -> ResearchResult:
        fields = []
        for index, _ in enumerate(request.origins):
            fields += [
                field(f"flights.{index}.airline", "Mock Air"),
                field(f"flights.{index}.duration", "5 hours"),
                field(f"flights.{index}.price_per_person", sar=fare),
            ]
        for index, _ in enumerate(request.cities):
            fields += [
                field(f"cities.{index}.hotel_name", "Mock Hotel"),
                field(f"cities.{index}.hotel_price_per_night", sar=night),
            ]
        return ResearchResult(
            fields=fields,
            sources=[
                ResearchSource(
                    id=1, title="T", url="https://example.com/a", content="C"
                )
            ],
            cost=ResearchCost(tavily_searches=len(request.origins) + 1),
        )

    return research


def fake_planner(monkeypatch: pytest.MonkeyPatch, *plans) -> list[str]:
    """Each call returns the next plan, or raises it if it is an error."""
    remaining = list(plans)
    payloads: list[str] = []

    async def plan(contents, system_prompt, schema, config, cost):
        payloads.append(contents)
        cost.gemini_requests += 1
        result = remaining.pop(0)
        if isinstance(result, Exception):
            raise result
        return TripPlan(feasible=True, blocking_categories=[], options=result)

    monkeypatch.setattr(proposal_generation, "call_gemini", plan)
    return payloads


def run(generation: GenerationInput, tmp_path: Path):
    return asyncio.run(generate_proposals(generation, settings(tmp_path)))


THREE = [option("Istanbul"), option("Baku"), option("Tbilisi")]


def test_three_distinct_proposals_are_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_planner(monkeypatch, THREE)
    monkeypatch.setattr(trip_research, "research", fake_research())

    result = run(group(), tmp_path)

    assert result.complete and result.message is None
    assert [p.option_number for p in result.proposals] == [1, 2, 3]
    assert {p.destination for p in result.proposals} == {"Istanbul", "Baku", "Tbilisi"}
    assert all(p.budget_status == "within_group_budget" for p in result.proposals)
    assert [r.origin for r in result.proposals[0].flights] == ["Riyadh", "Jeddah"]


def test_planner_never_receives_members_or_departure_cities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payloads = fake_planner(monkeypatch, THREE)
    monkeypatch.setattr(trip_research, "research", fake_research())

    run(group(), tmp_path)

    assert "Member" not in payloads[0]
    assert "Riyadh" not in payloads[0]
    assert '"budget_ceiling_sar": "3000"' in payloads[0]
    assert "5000" not in payloads[0]


def test_over_budget_option_is_regenerated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_planner(monkeypatch, THREE, [option("Doha")], [option("Muscat")])
    fares = iter(["9000", "9000", "1000", "1000", "1000"])

    async def research(request, config):
        return await fake_research(fare=next(fares))(request, config)

    monkeypatch.setattr(trip_research, "research", research)

    result = run(group(), tmp_path)

    assert result.complete
    assert result.proposals[0].destination == "Muscat"


def test_missing_prices_are_kept_and_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_planner(monkeypatch, THREE)

    async def research(request, config):
        result = await fake_research()(request, config)
        for item in result.fields:
            if "price" in item.field_id:
                item.value, item.status = None, "Not available"
                item.evidence, item.amount_sar = [], None
        return result

    monkeypatch.setattr(trip_research, "research", research)

    result = run(group(), tmp_path)

    assert result.complete
    assert result.proposals[0].budget_status == "includes_unconfirmed"


def test_failed_option_stops_after_two_regenerations_and_returns_the_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = date(2026, 11, 1)
    payloads = fake_planner(
        monkeypatch,
        [option("Baku"), option("Tbilisi")],
        [option("A", start=outside)],
        [option("B", start=outside)],
        [option("C", start=outside)],
    )
    monkeypatch.setattr(trip_research, "research", fake_research())

    result = run(group(), tmp_path)

    assert len(result.proposals) == 2
    assert not result.complete
    assert "2 of 3" in result.message
    assert result.failures[0].reasons == ["dates_outside_shared_range"]
    assert len(payloads) == 4


def test_essential_not_met_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    essential = {"value": "Direct flights", "importance": "Essential"}
    good = [RequirementCheck(requirement_id="R1", met=True, explanation=None)]
    bad = [RequirementCheck(requirement_id="R1", met=False, explanation="Not found")]
    fake_planner(
        monkeypatch,
        [
            option("Bad", checks=bad),
            option("Baku", checks=good),
            option("Tbilisi", checks=good),
        ],
        [option("Muscat", checks=good)],
    )
    monkeypatch.setattr(trip_research, "research", fake_research())

    result = run(group(flights=essential), tmp_path)

    assert {p.destination for p in result.proposals} == {"Muscat", "Baku", "Tbilisi"}


def test_essential_wins_when_members_share_a_preference() -> None:
    generation = group(flights={"value": "Direct", "importance": "Essential"})
    generation.members[1].flights.value = "direct"

    [requirement] = collect_requirements(generation)

    assert requirement.importance == "Essential"


def test_unmet_flexible_needs_an_explanation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    flexible = {"value": "Museums", "importance": "Flexible"}
    silent = [RequirementCheck(requirement_id="R1", met=False, explanation=None)]
    explained = [
        RequirementCheck(
            requirement_id="R1", met=False, explanation="Outdoor sights fit better."
        )
    ]
    fake_planner(
        monkeypatch,
        [
            option("Silent", checks=silent),
            option("Baku", checks=explained),
            option("Tbilisi", checks=explained),
        ],
        [option("Muscat", checks=explained)],
    )
    monkeypatch.setattr(trip_research, "research", fake_research())

    result = run(group(interests=flexible), tmp_path)

    assert result.complete
    adjustment = result.proposals[0].flexible_adjustments[0]
    assert (adjustment.category, adjustment.explanation) == (
        "interests",
        "Outdoor sights fit better.",
    )


@pytest.mark.parametrize(
    "text",
    ["Stay under 3,000", "Under ٣٠٠٠ for all", "Fits 5000", "Flying from Jeddah"],
)
def test_private_figures_and_cities_are_found(text: str) -> None:
    assert contains_private_detail(text, group())


def test_general_text_is_allowed() -> None:
    assert not contains_private_detail("Suits the group's budget", group())


def test_title_with_a_member_budget_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_planner(
        monkeypatch,
        [option("Leak", title="Trip under 3000"), option("Baku"), option("Tbilisi")],
        [option("Muscat")],
    )
    monkeypatch.setattr(trip_research, "research", fake_research())

    result = run(group(), tmp_path)

    assert {p.destination for p in result.proposals} == {"Muscat", "Baku", "Tbilisi"}


def test_duplicate_route_is_not_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_planner(
        monkeypatch,
        [option("Baku"), option("baku"), option("Tbilisi")],
        [option("Muscat")],
    )
    monkeypatch.setattr(trip_research, "research", fake_research())

    result = run(group(), tmp_path)

    assert len({p.destination.casefold() for p in result.proposals}) == 3


def test_quota_during_generation_returns_what_succeeded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_planner(monkeypatch, THREE)
    good = fake_research()
    calls = 0

    async def research(request, config):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise ResearchError(
                "search_quota", "The Tavily plan limit has been reached."
            )
        return await good(request, config)

    monkeypatch.setattr(trip_research, "research", research)

    result = run(group(), tmp_path)

    assert len(result.proposals) == 1
    assert "Tavily plan limit" in result.message
    assert calls == 2


def test_quota_with_no_proposals_raises_a_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_planner(monkeypatch, ResearchError("model_quota", "The Gemini quota."))

    with pytest.raises(ResearchError) as caught:
        run(group(), tmp_path)

    assert caught.value.code == "model_quota"


def test_logs_hold_no_private_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    outside = date(2026, 11, 1)
    fake_planner(
        monkeypatch,
        [option("Secret place", start=outside), option("Baku"), option("Tbilisi")],
        [option("A", start=outside)],
        [option("B", start=outside)],
    )
    monkeypatch.setattr(trip_research, "research", fake_research())

    with caplog.at_level(logging.INFO):
        run(group(), tmp_path)

    logs = " ".join(caplog.messages)
    assert "generation_option_failed" in logs
    for private in ("Secret", "Riyadh", "Jeddah", "3000", "5000"):
        assert private not in logs


class FakeModels:
    def __init__(self, outcomes: list) -> None:
        self.outcomes = outcomes
        self.calls = 0

    async def generate_content(self, **kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(text=outcome, usage_metadata=None)


def run_gemini(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, outcomes: list
) -> tuple[object, FakeModels, list[float], ResearchCost]:
    models = FakeModels(outcomes)
    sleeps: list[float] = []

    async def no_wait(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(trip_research.asyncio, "sleep", no_wait)
    monkeypatch.setattr(
        trip_research.genai,
        "Client",
        lambda **kwargs: SimpleNamespace(aio=SimpleNamespace(models=models)),
    )
    cost = ResearchCost()
    try:
        outcome = asyncio.run(call_gemini("x", "y", TripPlan, settings(tmp_path), cost))
    except ResearchError as error:
        outcome = error
    return outcome, models, sleeps, cost


def api_error(code: int) -> genai_errors.APIError:
    return genai_errors.APIError(code, {"error": {"message": "secret detail"}})


def test_quota_waits_retries_once_then_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outcome, models, sleeps, cost = run_gemini(
        monkeypatch, tmp_path, [api_error(429), EMPTY_PLAN]
    )

    assert outcome == TripPlan(feasible=True, blocking_categories=[], options=[])
    assert (models.calls, cost.gemini_requests) == (2, 2)
    assert len(sleeps) == 1


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (api_error(429), "model_quota"),
        (api_error(503), "model_unavailable"),
        (ConnectionError("down"), "model_unavailable"),
    ],
)
def test_second_failure_returns_a_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: Exception, code: str
) -> None:
    outcome, models, _, _ = run_gemini(monkeypatch, tmp_path, [failure, failure])

    assert isinstance(outcome, ResearchError)
    assert outcome.code == code
    assert models.calls == 2
    assert "secret detail" not in outcome.message


def test_bad_request_is_not_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outcome, models, sleeps, _ = run_gemini(monkeypatch, tmp_path, [api_error(400)])

    assert outcome.code == "model_unavailable"
    assert (models.calls, sleeps) == (1, [])


def test_failed_calls_log_status_and_class_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app.services.trip_research"):
        run_gemini(monkeypatch, tmp_path, [api_error(400)])
        run_gemini(monkeypatch, tmp_path, [ConnectionError("down"), EMPTY_PLAN])

    lines = [m for m in caplog.messages if m.startswith("gemini_call_failed")]
    assert lines[0].startswith("gemini_call_failed attempt=1 status=400 error=APIError")
    assert "status=none error=ConnectionError" in lines[1]
    # A rejected request is told apart from an outage, and no body is logged.
    assert not any("secret detail" in m or "down" in m for m in caplog.messages)


def test_invalid_json_is_reported_without_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outcome, models, _, _ = run_gemini(monkeypatch, tmp_path, ["not json"])

    assert outcome.code == "model_invalid_output"
    assert models.calls == 1


def test_outage_stops_generation_instead_of_trying_more_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_planner(monkeypatch, THREE)
    calls = 0
    good = fake_research()

    async def research(request, config):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise ResearchError("model_unavailable", "Gemini is unavailable.")
        return await good(request, config)

    monkeypatch.setattr(trip_research, "research", research)

    result = run(group(), tmp_path)

    assert calls == 2
    assert len(result.proposals) == 1
    assert "Gemini is unavailable." in result.message


MOCK = Path(__file__).resolve().parents[3] / "docs/examples/proposals.mock.json"


def test_demo_mode_is_off_by_default() -> None:
    assert Settings(_env_file=None).proposals_demo_mode is False


def test_demo_mode_serves_saved_proposals_without_any_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fail(*args, **kwargs):
        raise AssertionError("Demo mode must not call Gemini or Tavily")

    monkeypatch.setattr(proposal_generation, "call_gemini", fail)
    monkeypatch.setattr(trip_research, "research", fail)
    config = settings(tmp_path).model_copy(
        update={"proposals_demo_mode": True, "proposals_demo_file": MOCK}
    )
    generation = group()

    result = asyncio.run(generate_proposals(generation, config, version=4))

    assert result.demo and result.complete
    assert "Demo mode" in result.message
    assert len(result.proposals) == 3
    assert all(item.trip_id == generation.trip_id for item in result.proposals)
    assert all(item.version == 4 for item in result.proposals)
    assert result.cost == ResearchCost()


def test_missing_demo_file_gives_a_clear_error(tmp_path: Path) -> None:
    config = settings(tmp_path).model_copy(
        update={
            "proposals_demo_mode": True,
            "proposals_demo_file": tmp_path / "missing.json",
        }
    )

    with pytest.raises(ResearchError) as caught:
        asyncio.run(generate_proposals(group(), config))

    assert caught.value.code == "not_configured"


def test_saved_demo_file_is_valid_and_holds_no_keys() -> None:
    demo = Settings(_env_file=None).proposals_demo_file.read_text(encoding="utf-8")

    assert len(ProposalSet.model_validate_json(demo).proposals) == 3
    for pattern in (
        r"AIza[0-9A-Za-z_-]{20,}",
        r"tvly-[0-9A-Za-z]{10,}",
        r"(?i)api.?key",
    ):
        assert re.search(pattern, demo) is None


def test_uncited_sources_are_removed_before_saving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_planner(monkeypatch, THREE)
    good = fake_research()

    async def research(request, config):
        result = await good(request, config)
        result.sources.append(
            ResearchSource(id=2, title="U", url="https://example.com/u", content="C")
        )
        return result

    monkeypatch.setattr(trip_research, "research", research)

    proposal = run(group(), tmp_path).proposals[0]

    assert [source.id for source in proposal.sources] == [1]


def test_unconfirmed_price_is_counted_and_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_planner(monkeypatch, THREE)

    async def research(request, config):
        result = await fake_research()(request, config)
        for item in result.fields:
            if "hotel_price" in item.field_id:
                item.status, item.evidence = "Unconfirmed", []
        return result

    monkeypatch.setattr(trip_research, "research", research)

    result = run(group(), tmp_path)

    assert result.proposals[0].budget_status == "includes_unconfirmed"
    price = result.proposals[0].cities[0].hotel_price_per_night
    assert (price.status, price.evidence) == ("Unconfirmed", [])


def test_unconfirmed_price_can_still_exceed_the_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_planner(
        monkeypatch,
        [option("Costly"), option("Baku"), option("Tbilisi")],
        [option("Muscat")],
    )
    fares = iter(["9000", "1000", "1000", "1000"])

    async def research(request, config):
        result = await fake_research(fare=next(fares))(request, config)
        for item in result.fields:
            if "flights" in item.field_id and "price" in item.field_id:
                item.status, item.evidence = "Unconfirmed", []
        return result

    monkeypatch.setattr(trip_research, "research", research)

    result = run(group(), tmp_path)

    assert "Costly" not in {p.destination for p in result.proposals}
    assert result.complete


def test_titles_in_both_languages_are_saved_and_blank_ones_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    named = option("Baku")
    named.title_ar = "\u0631\u062d\u0644\u0629 \u0647\u0627\u062f\u0626\u0629"
    named.title_en = "  "
    fake_planner(monkeypatch, [named, option("Tbilisi"), option("Yerevan")])
    monkeypatch.setattr(trip_research, "research", fake_research())

    first = run(group(), tmp_path).proposals[0]

    assert first.title_ar == named.title_ar
    assert first.title_en is None


def test_private_detail_in_a_translated_title_rejects_the_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    leaky = option("Baku")
    leaky.title_ar = "Trip under 5000"
    fake_planner(
        monkeypatch, [leaky, option("Tbilisi"), option("Yerevan")], [option("Doha")]
    )
    monkeypatch.setattr(trip_research, "research", fake_research())

    result = run(group(), tmp_path)

    assert "Baku" not in {item.destination for item in result.proposals}


def test_hotel_link_uses_hotel_city_country_dates_and_group_size() -> None:
    url = hotel_search_url(
        "Mock Hotel", "Cairo", "Egypt", date(2026, 12, 13), date(2026, 12, 17), 2
    )

    assert url == (
        "https://www.booking.com/searchresults.html?ss=Mock+Hotel%2C+Cairo%2C+Egypt"
        "&checkin=2026-12-13&checkout=2026-12-17&group_adults=2&no_rooms=2"
    )


def test_unknown_hotel_searches_the_city_and_zero_nights_has_no_link() -> None:
    day = date(2026, 12, 13)

    assert "ss=Cairo%2C+Egypt" in hotel_search_url(
        None, "Cairo", "Egypt", day, date(2026, 12, 14), 2
    )
    assert hotel_search_url(None, "Cairo", "Egypt", day, day, 2) is None


def test_generated_hotels_get_consecutive_dates_and_all_members(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    two_cities = option("Georgia")
    two_cities.cities = [
        PlannedCity(city="Tbilisi", nights=3),
        PlannedCity(city="Batumi", nights=1),
    ]
    fake_planner(monkeypatch, [two_cities, option("Baku"), option("Tbilisi")])

    async def research(request, config):
        result = await fake_research()(request, config)
        result.fields += [
            field("intercity.0.mode", "Train"),
            field("intercity.0.duration", "5 hours"),
            field("intercity.0.price_per_person", sar="100"),
        ]
        return result

    monkeypatch.setattr(trip_research, "research", research)

    stays = run(group(), tmp_path).proposals[0].cities

    assert "checkin=2026-11-20&checkout=2026-11-23" in stays[0].booking_url
    assert "checkin=2026-11-23&checkout=2026-11-24" in stays[1].booking_url
    assert "group_adults=2" in stays[1].booking_url


def test_one_way_fare_reports_includes_unconfirmed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_planner(monkeypatch, THREE)
    leg = FareLeg(
        "outbound", "2026-11-20", "Saudia", 200, "1000", "SAR", "https://a.example/out"
    )

    async def research(request, config):
        result = await fake_research()(request, config)
        result.fares = {
            index: FlightFare(
                "Saudia", 200, "1000", "SAR", False, "Saudia", "one_way", (leg,)
            )
            for index in range(len(request.origins))
        }
        return result

    monkeypatch.setattr(trip_research, "research", research)

    proposal = run(group(), tmp_path).proposals[0]

    route = proposal.flights[0]
    assert route.trip_type == "one_way"
    assert route.legs[0].booking_url == "https://a.example/out"
    assert route.legs[0].price.amount_sar == Decimal("1000.00")
    assert proposal.budget_status == "includes_unconfirmed"


def test_web_search_flight_has_null_booking_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_planner(monkeypatch, THREE)
    monkeypatch.setattr(trip_research, "research", fake_research())

    route = run(group(), tmp_path).proposals[0].flights[0]

    assert route.trip_type == "round_trip"
    assert [leg.booking_url for leg in route.legs] == [None, None]


def counted_research(**kwargs):
    good = fake_research(**kwargs)

    async def research(request, config):
        result = await good(request, config)
        result.cost.gemini_requests = 1
        return result

    return research


def test_planner_is_told_to_offer_cities_in_the_same_country() -> None:
    prompt = proposal_generation.PLANNER_PROMPT
    assert "different cities in the same country" in prompt
    assert "Only when destinations are Flexible" in prompt


def test_duplicate_gets_one_explicit_retry_then_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payloads = fake_planner(
        monkeypatch,
        [option("Baku"), option("Baku"), option("Tbilisi")],
        [option("Baku")],
    )
    monkeypatch.setattr(trip_research, "research", fake_research())

    result = run(group(), tmp_path)

    assert len(payloads) == 2
    retry = json.loads(payloads[1])
    assert retry["previous_problem"] == "duplicate_route"
    assert "baku" in [route["destination"] for route in retry["avoid_routes"]]
    assert result.failures[0].reasons == ["duplicate_route"]
    assert len(result.proposals) == 2


def test_same_cities_under_another_name_are_a_duplicate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    renamed = option("Baku")
    renamed.destination = "Azerbaijan break"
    fake_planner(
        monkeypatch, [option("Baku"), renamed, option("Tbilisi")], [option("Muscat")]
    )
    monkeypatch.setattr(trip_research, "research", fake_research())

    result = run(group(), tmp_path)

    assert {p.destination for p in result.proposals} == {"Baku", "Muscat", "Tbilisi"}


def test_over_budget_retry_asks_for_something_cheaper_without_showing_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payloads = fake_planner(monkeypatch, THREE, [option("Muscat")])
    fares = iter(["9000", "1000", "1000", "1000"])

    async def research(request, config):
        return await fake_research(fare=next(fares))(request, config)

    monkeypatch.setattr(trip_research, "research", research)

    result = run(group(), tmp_path)

    assert json.loads(payloads[1])["previous_problem"] == "over_group_budget"
    assert json.loads(payloads[0])["previous_problem"] is None
    assert result.complete
    assert "3000" not in result.model_dump_json()


def test_gemini_call_limit_stops_and_returns_what_succeeded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    names = [f"Place {number}" for number in range(10)]
    payloads = fake_planner(
        monkeypatch,
        [option("Baku"), option("Tbilisi"), option(names[0])],
        *[[option(name)] for name in names[1:]],
    )
    fares = iter(["1000", "1000", *["9000"] * 10])

    async def research(request, config):
        return await counted_research(fare=next(fares))(request, config)

    monkeypatch.setattr(trip_research, "research", research)

    result = run(group(), tmp_path)

    assert len(result.proposals) == 2
    assert len(payloads) == 2
    assert result.cost.gemini_requests == 6
    assert "request limit" in result.message


def test_gemini_call_limit_comes_from_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_planner(monkeypatch, THREE)
    monkeypatch.setattr(trip_research, "research", counted_research())
    config = settings(tmp_path).model_copy(
        update={"max_gemini_calls_per_generation": 2}
    )

    result = asyncio.run(generate_proposals(group(), config))

    assert len(result.proposals) == 1
    assert Settings(_env_file=None).max_gemini_calls_per_generation == 7


def test_new_links_have_no_tracking_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_planner(monkeypatch, THREE)

    async def research(request, config):
        result = await fake_research()(request, config)
        result.sources[0].url = "https://example.com/a?gclid=1&gclsrc=gf&keep=2"
        return result

    monkeypatch.setattr(trip_research, "research", research)

    body = run(group(), tmp_path).proposals[0].model_dump_json()

    assert "gclid" not in body and "gclsrc" not in body
    assert "keep=2" in body


def _fit_input(*members):
    base = {"departure_city": "Riyadh", "max_budget_sar": "5000"}
    return GenerationInput(
        trip_id=UUID("00000000-0000-4000-8000-0000000000aa"),
        shared_start=date(2026, 11, 20),
        shared_end=date(2026, 11, 24),
        members=[
            {"label": f"Member {n}", **base, **m} for n, m in enumerate(members, 1)
        ],
    )


def test_fit_scores_each_member_and_keeps_only_the_average_and_the_least() -> None:
    from app.services.proposal_generation import proposal_fit

    generation = _fit_input(
        {"destinations": {"value": "Paris", "importance": "Essential"}},
        {"interests": {"value": "museums", "importance": "Flexible"}},
        {},
    )
    requirements = collect_requirements(generation)
    paris = option("Paris")
    ids = {item.text: item.id for item in requirements}
    checks = [
        RequirementCheck(requirement_id=ids["Paris"], met=True, explanation=None),
        RequirementCheck(requirement_id=ids["museums"], met=False, explanation="x"),
    ]
    planned = paris.model_copy(update={"requirement_checks": checks})

    fit = proposal_fit(planned, generation, requirements, "within_group_budget")

    # Member 1: Paris met (3) + dates/budget (6) = 9/9 = 100.
    # Member 2: museums not met (0 of 1) + 6 = 6/7 = 86. Member 3: 6/6 = 100.
    assert fit.least_satisfied_percent == 86
    assert fit.group_percent == 95
    assert fit.member_count == 3
    dumped = fit.model_dump_json()
    assert "Paris" not in dumped and "museums" not in dumped and "Member" not in dumped


def test_fit_counts_unverified_as_half_and_unconfirmed_budget_as_half() -> None:
    from app.services.proposal_generation import proposal_fit

    generation = _fit_input(
        {"interests": {"value": "beaches", "importance": "Essential"}}
    )
    requirements = collect_requirements(generation)
    planned = option("Doha").model_copy(
        update={
            "requirement_checks": [
                RequirementCheck(
                    requirement_id=requirements[0].id, met=True, explanation=None
                )
            ]
        }
    )

    fit = proposal_fit(planned, generation, requirements, "includes_unconfirmed")

    # beaches: AI says met but code cannot check -> 0.5 * 3; dates 3; budget 0.5 * 3.
    assert fit.least_satisfied_percent == fit.group_percent == 67


def test_focus_tags_keep_known_tags_only_with_a_default() -> None:
    from app.services.proposal_generation import focus_tags

    assert focus_tags(["Food", "beaches_water", "food", "medical"]) == [
        "food",
        "beaches_water",
    ]
    assert focus_tags([]) == ["landmarks", "food"]
    assert (
        len(
            focus_tags(
                list(
                    __import__(
                        "app.schemas.proposals", fromlist=["x"]
                    ).ACTIVITY_FOCUS_TAGS
                )
            )
        )
        == 4
    )
