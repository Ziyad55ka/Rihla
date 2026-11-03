import asyncio
import json
from copy import deepcopy
from decimal import Decimal

import pytest
from activity_fixture import mock_data

from app.core.config import Settings
from app.schemas.costs import CostAmount
from app.schemas.proposals import Proposal
from app.services import activity_research as ar
from app.services.proposal_costs import CostContext, proposal_costs
from app.services.trip_research import ResearchError, ResearchSource

CONTENT = (
    "City Museum. Historic exhibits. Downtown. 2 hours. "
    "Admission 20 USD per person. Outdoor walk. Free entry. "
    "Festival on 2026-01-01."
)


def text(value=None, quote=None, source_id=10):
    return {"value": value, "quote": quote, "source_id": source_id}


def draft(**updates):
    item = dict(
        city_order=1,
        category="attraction",
        name=text("City Museum", CONTENT),
        description=text("Historic exhibits", CONTENT),
        location=text("Downtown", CONTENT),
        duration=text("2 hours", CONTENT),
        scheduled_date=text(),
        is_event=False,
        price={
            "amount": "20",
            "currency": "USD",
            "source_id": 10,
            "quote": "Admission 20 USD per person.",
        },
    )
    return ar.Suggestion.model_validate({**item, **updates})


def proposal():
    p = Proposal.model_validate(mock_data()["proposals"][0])
    for stay in p.cities:
        stay.activities = []
    return p


@pytest.fixture
def source():
    return {
        10: ResearchSource(
            id=10,
            title="Official museum",
            url="https://museum.example/",
            content=CONTENT,
        )
    }


def test_prices_are_evidence_backed_converted_and_never_sourced(source):
    price = ar._price(draft().price, source)
    assert price.amount_sar == Decimal("75.00")
    assert price.status == "Estimated"
    for changes in [
        dict(amount="900"),
        dict(currency="TRY"),
        dict(quote="Invented quote 20 USD"),
        dict(source_id=999),
    ]:
        d = draft().price.model_copy(update=changes)
        assert ar._price(d, source).amount_sar is None


def test_free_is_not_inferred_from_missing_cost(source):
    free = draft().price.model_copy(update={"amount": "0", "quote": "Free entry."})
    assert ar._price(free, source).amount_sar == 0
    assert (
        ar._price(free.model_copy(update={"quote": "City Museum."}), source).amount_sar
        is None
    )


def test_fabricated_or_cross_city_text_is_not_shown(source):
    assert (
        ar._text(ar.CitedText(**text("Invented museum", CONTENT)), source).value is None
    )
    assert (
        ar._text(ar.CitedText(**text("City Museum", CONTENT, 999)), source).value
        is None
    )


def test_no_keys_means_error_and_never_mock_data():
    with pytest.raises(ResearchError, match="not configured"):
        asyncio.run(ar.find_activities(proposal(), Settings(_env_file=None)))


def test_real_search_uses_public_cities_only_and_discards_invalid_events(monkeypatch):
    p = proposal()
    calls = []

    async def search(query, settings, **kwargs):
        calls.append(query)
        return [
            ResearchSource(
                id=1, title="Museum", url="https://museum.example/", content=CONTENT
            )
        ], False

    async def extract(contents, prompt, schema, settings, cost):
        assert "max_budget" not in contents and "departure_city" not in contents
        source_id = max(s.id for s in p.sources) + 1
        first = draft().model_dump()
        for field in [
            "name",
            "description",
            "location",
            "duration",
            "scheduled_date",
            "price",
        ]:
            first[field]["source_id"] = source_id
        event = deepcopy(first)
        event.update(
            is_event=True, scheduled_date=text("2026-01-01", CONTENT, source_id)
        )
        return ar.Suggestions(suggestions=[first, first, event])

    monkeypatch.setattr(ar.research, "search_sources", search)
    monkeypatch.setattr(ar.research, "call_gemini", extract)
    settings = Settings(_env_file=None, tavily_api_key="fake", gemini_api_key="fake")
    result = asyncio.run(ar.find_activities(p, settings))
    assert len(result.cities[0].activities) == 1
    assert result.cities[0].activities[0].price_per_person.amount_sar == 75
    assert result.activity_research_status == "ready"
    assert len(calls) == len(p.cities)
    assert result.flights == p.flights
    assert Proposal.model_validate(result.model_dump()) == result


def test_selected_costs_join_existing_breakdown_and_unknown_is_partial():
    p = Proposal.model_validate(mock_data()["proposals"][0])
    museum, _, event, restaurant = p.cities[0].activities
    base = proposal_costs(p, Decimal(0), None, []).scenarios[0]
    selected = proposal_costs(p, Decimal(0), None, [museum.id, restaurant.id])
    line = next(
        part for part in selected.scenarios[0].lines if part.category == "activities"
    )
    assert line.counted and line.per_person.amount_sar == Decimal("150.50")
    assert selected.scenarios[
        0
    ].per_person_total.amount_sar == base.per_person_total.amount_sar + Decimal(
        "150.50"
    )
    unknown = proposal_costs(p, Decimal(0), None, [event.id]).scenarios[0]
    assert unknown.per_person_total.partial
    assert "activities_selected" in selected.assumptions


def test_group_activities_use_actual_members_choices_not_my_choices_times_members():
    p = Proposal.model_validate(mock_data()["proposals"][0])
    context = CostContext.model_validate(
        {
            "member_count": 3,
            "own_budget_sar": "10000",
            "origins": [{"origin": p.flights[0].origin, "members": 3}],
            "proposals": [{"id": p.id, "flights": [p.flights[0].model_dump()]}],
        }
    )
    group = CostAmount(amount_sar=Decimal("100.00"), status="Estimated")
    base = proposal_costs(
        p, Decimal(0), context, [], CostAmount(amount_sar=0, status="Estimated")
    )
    chosen = proposal_costs(
        p, Decimal(0), context, [p.cities[0].activities[0].id], group
    )
    assert len(chosen.scenarios) == 2
    for before, after in zip(base.scenarios, chosen.scenarios, strict=True):
        assert after.group_total.amount_sar - before.group_total.amount_sar == 100
        assert (
            after.per_person_total.amount_sar - before.per_person_total.amount_sar
            == Decimal("85.50")
        )


def test_gemini_schema_has_no_max_items():
    assert "maxItems" not in json.dumps(ar.Suggestions.model_json_schema())


def test_results_are_capped_per_city_and_in_total(monkeypatch):
    p = proposal()
    content = " ".join(f"Place {n:02d}." for n in range(60))
    source_id = max(s.id for s in p.sources) + 1

    async def search(query, settings, **kwargs):
        return [
            ResearchSource(
                id=1, title="Places", url="https://p.example/", content=content
            )
        ], False

    async def extract(contents, prompt, schema, settings, cost):
        items = []
        for stay in p.cities:
            for n in range(40):
                name = f"Place {n:02d}"
                items.append(
                    draft(
                        city_order=stay.order,
                        name=text(name, f"{name}.", source_id),
                    )
                )
        return ar.Suggestions(suggestions=items)

    monkeypatch.setattr(ar.research, "search_sources", search)
    monkeypatch.setattr(ar.research, "call_gemini", extract)
    settings = Settings(_env_file=None, tavily_api_key="fake", gemini_api_key="fake")
    result = asyncio.run(ar.find_activities(p, settings))
    assert len(result.cities[0].activities) == ar.MAX_PER_CITY == 12
    # The total cap also holds when the per-city cap would allow more.
    monkeypatch.setattr(ar, "MAX_PER_CITY", 100)
    monkeypatch.setattr(ar, "MAX_SUGGESTIONS", 15)
    result = asyncio.run(ar.find_activities(p, settings))
    assert len(result.cities[0].activities) == 15
