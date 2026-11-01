from copy import deepcopy
from datetime import timedelta

import pytest
from pydantic import ValidationError
from test_proposals_schema import mock_data

from app.schemas.activities import SelectionRequest
from app.schemas.proposals import Proposal


def test_legacy_proposals_have_empty_activities():
    data = mock_data()["proposals"][0]
    for city in data["cities"]:
        city.pop("activities")
    assert Proposal.model_validate(data).cities[0].activities == []


def test_activities_allow_free_prices_but_not_negative_or_sourced_prices():
    data = mock_data()["proposals"][0]
    assert (
        Proposal.model_validate(data)
        .cities[0]
        .activities[1]
        .price_per_person.amount_sar
        == 0
    )
    for amount in ("-1.00", "1.001"):
        bad = deepcopy(data)
        bad["cities"][0]["activities"][0]["price_per_person"]["amount_sar"] = amount
        with pytest.raises(ValidationError):
            Proposal.model_validate(bad)
    data["cities"][0]["activities"][0]["price_per_person"].update(
        status="Sourced", evidence=[{"source_id": 1, "quote": "Example"}]
    )
    with pytest.raises(ValidationError, match="live flight"):
        Proposal.model_validate(data)


def test_activity_evidence_is_validated_and_preserved():
    data = mock_data()["proposals"][0]
    activity = data["cities"][0]["activities"][0]
    data["sources"].append(
        {"id": 99, "title": "Activity", "url": "https://example.test"}
    )
    activity["description"].update(
        status="Estimated", evidence=[{"source_id": 99, "quote": "Example"}]
    )
    assert any(
        s.id == 99
        for s in Proposal.model_validate(data).without_uncited_sources().sources
    )
    activity["description"]["evidence"][0]["source_id"] = 999
    with pytest.raises(ValidationError, match="listed source"):
        Proposal.model_validate(data)


def test_duplicate_ids_and_out_of_stay_events_are_rejected():
    data = mock_data()["proposals"][0]
    first, second = data["cities"][0]["activities"][:2]
    second["id"] = first["id"]
    with pytest.raises(ValidationError, match="unique"):
        Proposal.model_validate(data)
    second["id"] = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    parsed = Proposal.model_validate(data)
    first["scheduled_date"].update(
        value=(parsed.end_date + timedelta(days=1)).isoformat(), status="Unconfirmed"
    )
    with pytest.raises(ValidationError, match="city stay"):
        Proposal.model_validate(data)


def test_selection_request_rejects_duplicate_and_malformed_ids():
    activity_id = mock_data()["proposals"][0]["cities"][0]["activities"][0]["id"]
    for ids in ([activity_id, activity_id], ["invalid"]):
        with pytest.raises(ValidationError):
            SelectionRequest(version=1, activity_ids=ids)


def test_every_city_in_demo_has_activities_attractions_and_restaurants():
    from app.schemas.proposals import ProposalSet

    data = ProposalSet.model_validate(mock_data())
    for proposal in data.proposals:
        for stay in proposal.cities:
            assert {a.category for a in stay.activities} == {
                "activity",
                "attraction",
                "restaurant",
            }


def test_category_is_backwards_compatible_but_rejects_unknown_values():
    data = mock_data()["proposals"][0]
    activity = data["cities"][0]["activities"][0]
    activity.pop("category")
    assert Proposal.model_validate(data).cities[0].activities[0].category == "activity"
    activity["category"] = "other"
    with pytest.raises(ValidationError):
        Proposal.model_validate(data)
