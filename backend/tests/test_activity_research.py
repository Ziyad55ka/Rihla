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
    # Three searches per city: things to do, fun experiences, then restaurants.
    assert len(calls) == 3 * len(p.cities)
    assert all("tourists" in q or "visitors" in q or "experiences" in q for q in calls)
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


# --- Redesign, 3 Nov 2026: tourist-only, matched to the group's interests ---

MIXED = (
    "City Museum. Historic exhibits. Old Market. Spice stalls. "
    "Cardiology Congress 2026. Annual medical meeting. Harbour Cruise. "
    "Sunset boat trip. Fish House. Grilled seafood. Fashion Mall. Big shops."
)


def _run(monkeypatch, items, focus=None):
    p = proposal()
    if focus is not None:
        p = p.model_copy(update={"activity_focus": focus})
    seen: dict = {}

    async def search(query, settings, **kwargs):
        seen.setdefault("queries", []).append((query, kwargs.get("include_domains")))
        return [
            ResearchSource(
                id=1, title="Guide", url="https://guide.example/", content=MIXED
            )
        ], False

    async def extract(contents, prompt, schema, settings, cost):
        seen["payload"] = contents
        sid = max(s.id for s in p.sources) + 1
        built = []
        for category, name, desc, extra in items:
            built.append(
                draft(
                    category=category,
                    name=text(name, MIXED, sid),
                    description=text(desc, MIXED, sid),
                    location=text(None, None, None),
                    duration=text(None, None, None),
                    price={
                        "amount": None,
                        "currency": None,
                        "source_id": None,
                        "quote": None,
                    },
                    **extra,
                ).model_dump()
            )
        return ar.Suggestions(suggestions=built)

    monkeypatch.setattr(ar.research, "search_sources", search)
    monkeypatch.setattr(ar.research, "call_gemini", extract)
    settings = Settings(_env_file=None, tavily_api_key="fake", gemini_api_key="fake")
    return asyncio.run(ar.find_activities(p, settings)), seen


def test_professional_and_medical_events_are_never_suggested(monkeypatch):
    result, _ = _run(
        monkeypatch,
        [
            ("activity", "Cardiology Congress 2026", "Annual medical meeting", {}),
            ("attraction", "City Museum", "Historic exhibits", {}),
            ("activity", "Harbour Cruise", "Sunset boat trip", {"tourist": False}),
        ],
    )
    names = [a.name.value for a in result.cities[0].activities]
    assert names == ["City Museum"]


def test_group_interests_rank_first_and_are_shown(monkeypatch):
    result, seen = _run(
        monkeypatch,
        [
            ("attraction", "City Museum", "Historic exhibits", {"fits": []}),
            (
                "activity",
                "Harbour Cruise",
                "Sunset boat trip",
                {"fits": ["beaches_water", "not_a_tag"]},
            ),
        ],
        focus=["beaches_water", "food"],
    )
    first = result.cities[0].activities[0]
    assert first.name.value == "Harbour Cruise" and first.fits == ["beaches_water"]
    assert '"group_focus": ["beaches_water", "food"]' in seen["payload"]
    things_to_do, fun, food = seen["queries"][:3]
    assert "boat trips" in things_to_do[0] and "tripadvisor.com" in things_to_do[1]
    assert "water parks" in fun[0] and "escape rooms" in fun[0]
    assert "restaurants" in food[0]


def test_each_city_keeps_a_fair_mix_of_categories(monkeypatch):
    many = [("restaurant", "Fish House", "Grilled seafood", {})] * 1
    attractions = [
        ("attraction", name, desc, {})
        for name, desc in [
            ("City Museum", "Historic exhibits"),
            ("Old Market", "Spice stalls"),
            ("Fashion Mall", "Big shops"),
        ]
    ]
    result, _ = _run(monkeypatch, attractions + many)
    categories = [a.category for a in result.cities[0].activities]
    assert categories.count("attraction") == 3 and categories.count("restaurant") == 1
    assert len(categories) <= ar.PER_CITY


def test_older_proposals_without_focus_use_general_sightseeing(monkeypatch):
    _, seen = _run(
        monkeypatch, [("attraction", "City Museum", "Historic exhibits", {})]
    )
    assert '"group_focus": ["landmarks", "food"]' in seen["payload"]


def test_off_topic_words_in_english_and_arabic():
    assert ar.off_topic("International Dental Summit")
    assert ar.off_topic("مؤتمر الأطباء")
    assert not ar.off_topic("Museum of Islamic Art")
    assert not ar.off_topic("Art exhibition at the National Gallery")


def test_gemini_schema_has_no_list_limit():
    import json as _json

    assert "maxItems" not in _json.dumps(ar.Suggestions.model_json_schema())


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
                        category=("attraction", "activity", "restaurant")[n % 3],
                        name=text(name, f"{name}.", source_id),
                    )
                )
        return ar.Suggestions(suggestions=items)

    monkeypatch.setattr(ar.research, "search_sources", search)
    monkeypatch.setattr(ar.research, "call_gemini", extract)
    settings = Settings(_env_file=None, tavily_api_key="fake", gemini_api_key="fake")
    result = asyncio.run(ar.find_activities(p, settings))
    # 6 attractions + 4 activities + 4 restaurants would be 14; the city cap is 12.
    assert len(result.cities[0].activities) == ar.PER_CITY == 12
    # The total cap also holds when the per-city caps would allow more.
    monkeypatch.setattr(ar, "PER_CITY", 100)
    monkeypatch.setattr(
        ar, "PER_CITY_LIMITS", {"attraction": 100, "activity": 100, "restaurant": 100}
    )
    monkeypatch.setattr(ar, "TOTAL", 15)
    result = asyncio.run(ar.find_activities(p, settings))
    assert len(result.cities[0].activities) == 15


def test_counts_log_holds_only_integers_and_model(monkeypatch, caplog):
    p = proposal()

    async def search(query, settings, **kwargs):
        return [
            ResearchSource(
                id=1, title="Museum", url="https://museum.example/", content=CONTENT
            )
        ], False

    async def extract(contents, prompt, schema, settings, cost):
        sid = max(s.id for s in p.sources) + 1
        good = draft().model_dump()
        for f in [
            "name",
            "description",
            "location",
            "duration",
            "scheduled_date",
            "price",
        ]:
            good[f]["source_id"] = sid
        paraphrased = deepcopy(good)
        paraphrased["name"]["quote"] = "words not in the page"
        bad_source = deepcopy(good)
        bad_source["name"]["source_id"] = 999
        shop = deepcopy(good)
        shop["category"] = "shopping"
        return ar.Suggestions(suggestions=[good, paraphrased, bad_source, shop])

    monkeypatch.setattr(ar.research, "search_sources", search)
    monkeypatch.setattr(ar.research, "call_gemini", extract)
    settings = Settings(_env_file=None, tavily_api_key="fake", gemini_api_key="fake")
    with caplog.at_level("INFO", logger=ar.__name__):
        asyncio.run(ar.find_activities(p, settings))
    [line] = [
        r.getMessage()
        for r in caplog.records
        if "activity_research_counts" in r.getMessage()
    ]
    fields = dict(part.split("=", 1) for part in line.split()[1:])
    assert list(fields) == [
        "raw",
        "kept",
        "dropped_category",
        "dropped_offtopic",
        "dropped_quote",
        "dropped_source",
        "dropped_date",
        "dropped_price",
        "focus",
        "model",
    ]
    assert fields.pop("model") == settings.gemini_model
    # Focus holds only fixed tag names, never the members' own words.
    assert fields.pop("focus") == "landmarks,food"
    assert all(v.isdigit() for v in fields.values())
    assert fields == {
        "raw": "4",
        "kept": "1",
        "dropped_category": "1",
        "dropped_offtopic": "0",
        "dropped_quote": "1",
        "dropped_source": "1",
        "dropped_date": "0",
        "dropped_price": "0",
    }
    assert "Museum" not in line and CONTENT[:20] not in line


def test_no_stated_price_falls_back_to_a_rough_typical_one():
    from decimal import Decimal

    from app.services.activity_research import typical_price

    assert (typical_price(120).amount_sar, typical_price(120).status) == (
        Decimal(120),
        "Unconfirmed",
    )
    assert typical_price(0).amount_sar == 0
    assert typical_price(None).status == "Not available"
