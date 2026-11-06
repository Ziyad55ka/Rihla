"""US-13 costs, US-14 source times and US-15 compatibility. All offline."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.routes import proposals as routes
from app.core.config import Settings
from app.main import create_app
from app.schemas.proposals import CompatibilityCheck, Proposal
from app.services.generation_inputs import GenerationInputsError, fetch_cost_context
from app.services.proposal_costs import CostContext, proposal_costs
from app.services.proposal_generation import (
    PlannedCity,
    PlannedOption,
    Requirement,
    RequirementCheck,
    compatibility_checks,
    destination_matches,
)
from app.services.supabase import get_supabase_http

MOCK = Path(__file__).resolve().parents[3] / "docs/examples/proposals.mock.json"
USER = "11111111-1111-4111-8111-111111111111"
TRIP = "00000000-0000-4000-8000-0000000000aa"
MEALS = Decimal(150)


def mock(index: int = 0) -> dict:
    return json.loads(MOCK.read_text(encoding="utf-8"))["proposals"][index]


def istanbul() -> Proposal:
    # Riyadh round trip 1200 Estimated, 4 nights at 450 Estimated, 5 days, no transfers.
    return Proposal.model_validate(mock(0))


def context(budget: str | None = "5000", members: int = 3, **extra) -> CostContext:
    proposal = mock(0)
    return CostContext.model_validate(
        {
            "member_count": members,
            "own_budget_sar": budget,
            "origins": [{"origin": "riyadh", "members": members}],
            "proposals": [{"id": proposal["id"], "flights": proposal["flights"]}],
            **extra,
        }
    )


def scenario(costs, rooms: str):
    return next(item for item in costs.scenarios if item.rooms == rooms)


def line(plan, category: str):
    return next(item for item in plan.lines if item.category == category)


# US-13-AC01: every category is listed, with activities shown but not counted yet.
def test_breakdown_lists_every_category_for_one_member() -> None:
    costs = proposal_costs(istanbul(), MEALS, context())
    single = scenario(costs, "single")

    assert [item.category for item in single.lines] == [
        "flights",
        "accommodation",
        "activities",
        "meals",
    ]
    assert line(single, "flights").per_person.amount_sar == Decimal("1200.00")
    assert line(single, "accommodation").per_person.amount_sar == Decimal("1800.00")
    assert line(single, "meals").per_person.amount_sar == Decimal("750.00")
    assert line(single, "meals").per_person.status == "Unconfirmed"
    assert line(single, "activities").counted is False
    assert single.per_person_total.amount_sar == Decimal("3750.00")
    # The meal allowance has no source, so the total is never better than Unconfirmed.
    assert single.per_person_total.status == "Unconfirmed"
    assert (costs.days, costs.nights) == (5, 4)


# US-13-AC02: per person and group, for single and shared rooms, with assumptions.
def test_group_total_and_shared_rooms() -> None:
    costs = proposal_costs(istanbul(), MEALS, context(members=3))
    single, shared = scenario(costs, "single"), scenario(costs, "shared")

    assert single.group_total.amount_sar == Decimal("11250.00")
    # Three people need two rooms: 1800 x 2 split three ways is 1200 each.
    assert line(shared, "accommodation").per_person.amount_sar == Decimal("1200.00")
    assert shared.per_person_total.amount_sar == Decimal("3150.00")
    assert shared.group_total.amount_sar == Decimal("9450.00")
    assert {"rooms_single", "rooms_shared", "meals_allowance"} <= set(costs.assumptions)
    assert "group_total_all_cities" in costs.assumptions


def test_group_total_marks_a_city_without_flights_as_partial() -> None:
    data = context()
    data.origins.append(type(data.origins[0])(origin="Jeddah", members=1))
    single = scenario(proposal_costs(istanbul(), MEALS, data), "single")

    assert single.group_total.partial is True


# US-13-AC03: the member's own budget, as a label, and the gap only when over.
@pytest.mark.parametrize(
    ("budget", "expected", "over_by"),
    [
        ("5000", "within", None),
        ("3000", "over", Decimal("750.00")),
        (None, "unknown", None),
    ],
)
def test_own_budget_warning(budget, expected, over_by) -> None:
    single = scenario(proposal_costs(istanbul(), MEALS, context(budget)), "single")

    assert (single.own_budget, single.over_by_sar) == (expected, over_by)


def test_uncertain_main_prices_cannot_be_called_within_budget() -> None:
    # Tbilisi and Batumi: Unconfirmed and missing prices, and no flight price.
    proposal = Proposal.model_validate(mock(1))
    data = context("99999")
    data.proposals = []
    single = scenario(proposal_costs(proposal, MEALS, data), "single")

    assert single.own_budget == "unconfirmed"
    assert line(single, "flights").per_person.status == "Not available"
    assert line(single, "accommodation").per_person.partial is True


def test_without_group_context_the_member_still_gets_own_costs() -> None:
    costs = proposal_costs(istanbul(), MEALS, None)

    assert [item.rooms for item in costs.scenarios] == ["single"]
    assert costs.scenarios[0].group_total is None
    assert costs.scenarios[0].own_budget == "unknown"
    assert "group_total_unavailable" in costs.assumptions


def test_member_without_own_flights_is_told() -> None:
    data = mock(0)
    data["flights"] = []
    costs = proposal_costs(Proposal.model_validate(data), MEALS, None)

    assert "flights_missing" in costs.assumptions
    assert line(costs.scenarios[0], "flights").per_person.amount_sar is None


# US-15-AC01/AC02: met, unverified and unmet, by topic only.
def planned(destination: str, checks: dict[str, bool]) -> PlannedOption:
    return PlannedOption(
        title="A relaxed city break",
        title_ar=None,
        title_en=None,
        destination_ar="إيطاليا",
        cities_ar=["روما"],
        destination=destination,
        country="Italy",
        arrival_airport=None,
        start_date=date(2026, 11, 20),
        end_date=date(2026, 11, 24),
        cities=[PlannedCity(city="Rome", nights=4)],
        requirement_checks=[
            RequirementCheck(requirement_id=key, met=value, explanation=None)
            for key, value in checks.items()
        ],
    )


def requirement(id: str, category: str, importance: str, text: str) -> Requirement:
    return Requirement(id=id, category=category, importance=importance, text=text)


def test_compatibility_checks_destinations_in_code_and_trusts_nothing_else() -> None:
    requirements = [
        requirement("R1", "destinations", "Essential", "France, Italy"),
        requirement("R2", "accommodation", "Essential", "Private rooms"),
        requirement("R3", "interests", "Flexible", "Beaches"),
    ]
    option = planned("Italy", {"R1": True, "R2": True, "R3": False})

    checks = {
        (item.topic, item.importance): item.status
        for item in compatibility_checks(option, requirements, "includes_unconfirmed")
    }

    assert checks == {
        ("destinations", "Essential"): "met",
        ("accommodation", "Essential"): "unverified",
        ("interests", "Flexible"): "unmet",
        ("dates", "Required"): "met",
        ("budget", "Required"): "unverified",
    }


def test_a_topic_shows_its_weakest_requirement_and_no_text() -> None:
    requirements = [
        requirement("R1", "destinations", "Flexible", "Rome"),
        requirement("R2", "destinations", "Flexible", "warm beach"),
    ]
    checks = compatibility_checks(
        planned("Italy", {"R1": True, "R2": True}), requirements, "within_group_budget"
    )

    assert checks[0].status == "unverified"
    assert checks[-1].status == "met"
    assert "beach" not in json.dumps([item.model_dump() for item in checks])


def test_ai_report_alone_never_counts_as_met_for_destinations() -> None:
    assert destination_matches("فرنسا أو إيطاليا", ["Italy", "إيطاليا"])
    assert destination_matches("Paris / Rome", ["Rome"])
    assert not destination_matches("somewhere warm", ["Rome", "Italy"])
    assert not destination_matches("Romania", ["Rome", "Italy"])


def test_compatibility_schema_rules() -> None:
    with pytest.raises(ValidationError, match="Required"):
        CompatibilityCheck(topic="budget", importance="Essential", status="met")
    data = mock(0)
    data["compatibility"] = [
        {"topic": "dates", "importance": "Required", "status": "met"},
        {"topic": "dates", "importance": "Required", "status": "met"},
    ]
    with pytest.raises(ValidationError, match="once"):
        Proposal.model_validate(data)


def test_older_proposals_without_new_fields_still_load() -> None:
    data = mock(0)
    data.pop("compatibility", None)
    for source in data["sources"]:
        source.pop("retrieved_at", None)

    proposal = Proposal.model_validate(data)
    assert proposal.compatibility == []


# The secret-key read: errors stay general, and the response is validated.
def test_cost_context_is_read_with_the_secret_key_only() -> None:
    seen = []

    def upstream(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, request.headers.get("apikey")))
        return httpx.Response(200, json=context().model_dump(mode="json"))

    settings = Settings(
        _env_file=None,
        supabase_url="https://supabase.example",
        supabase_secret_key="sb_secret_test",
    )
    result = _run(
        fetch_cost_context(
            UUID(TRIP), UUID(USER), settings, httpx.MockTransport(upstream)
        )
    )

    assert result.member_count == 3
    assert seen == [("/rest/v1/rpc/rihla_cost_context", "sb_secret_test")]


def _run(awaitable):
    import asyncio

    return asyncio.run(awaitable)


@pytest.fixture
def api(tmp_path):
    stored = {
        "version": 1,
        "complete": True,
        "generated_at": "2026-11-02T00:00:00Z",
        "generating": False,
        "needs_regeneration": False,
        "proposals": [mock(0)],
    }
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            generation_store_db=tmp_path / "store.sqlite3",
        )
    )

    async def fake_http():
        def upstream(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/auth/v1/user":
                return httpx.Response(200, json={"id": USER, "email": "a@b.test"})
            return httpx.Response(200, json=stored)

        async with httpx.AsyncClient(
            base_url="https://supabase.example/",
            transport=httpx.MockTransport(upstream),
        ) as client:
            yield client

    app.dependency_overrides[get_supabase_http] = fake_http
    client = TestClient(app)
    client.headers["Authorization"] = "Bearer current-user"
    return client


def test_reading_proposals_adds_costs_without_private_inputs(api, monkeypatch) -> None:
    async def fake_context(trip_id, member_id, settings):
        assert str(member_id) == USER
        return context("4321.00", members=3)

    monkeypatch.setattr(routes, "fetch_cost_context", fake_context)
    body = api.get(f"/api/trips/{TRIP}/proposals").json()

    costs = body["costs"][0]
    assert costs["proposal_id"] == mock(0)["id"]
    # The fixture's hotel source is not approved. The same hidden price must
    # also be excluded from costs rather than silently counted.
    assert (
        body["proposals"][0]["cities"][0]["hotel_price_per_night"]["amount_sar"] is None
    )
    assert costs["scenarios"][0]["group_total"]["amount_sar"] == "5850.00"
    assert costs["scenarios"][0]["group_total"]["partial"] is True
    text = json.dumps(body)
    # The member's budget and how many fly from each city never leave the backend.
    assert "4321" not in text
    assert "origins" not in text and "member_count" not in text


def test_reading_proposals_survives_a_failed_group_read(api, monkeypatch) -> None:
    async def failing(trip_id, member_id, settings):
        raise GenerationInputsError("unavailable")

    monkeypatch.setattr(routes, "fetch_cost_context", failing)
    response = api.get(f"/api/trips/{TRIP}/proposals")

    assert response.status_code == 200
    scenarios = response.json()["costs"][0]["scenarios"]
    assert scenarios[0]["group_total"] is None
    assert scenarios[0]["own_budget"] == "unknown"


def test_saved_activities_replace_the_planning_reserve() -> None:
    from app.schemas.proposals import SarPrice

    reserve = SarPrice(amount_sar=Decimal("675"), status="Unconfirmed", evidence=[])
    proposal = istanbul().model_copy(update={"activity_allowance_per_person": reserve})
    picked = [a for city in proposal.cities for a in city.activities][:1]
    before = proposal_costs(proposal, Decimal(150), context())
    assert line(scenario(before, "single"), "activities").per_person.amount_sar == 675
    assert "activities_allowance" in before.assumptions
    after = proposal_costs(proposal, Decimal(150), context(), [a.id for a in picked])
    chosen = sum((a.price_per_person.amount_sar or 0) for a in picked)
    activities = line(scenario(after, "single"), "activities").per_person
    assert activities.amount_sar == chosen and chosen < 675
    assert "activities_selected" in after.assumptions
