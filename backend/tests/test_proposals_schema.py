import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.proposals import (
    FlexibleAdjustment,
    InfoField,
    Proposal,
    ProposalSet,
)

MOCK = Path(__file__).resolve().parents[2] / "docs/examples/proposals.mock.json"


def mock_data() -> dict:
    return json.loads(MOCK.read_text(encoding="utf-8"))


def test_shared_mock_matches_the_schema() -> None:
    assert len(ProposalSet.model_validate(mock_data()).proposals) == 3


def test_identical_routes_are_rejected() -> None:
    data = mock_data()
    data["proposals"][2]["destination"] = data["proposals"][0]["destination"]
    data["proposals"][2]["cities"][0]["city"] = "Istanbul"

    with pytest.raises(ValidationError, match="differ"):
        ProposalSet.model_validate(data)


def test_nights_must_match_the_dates() -> None:
    data = mock_data()["proposals"][0]
    data["cities"][0]["nights"] = 2

    with pytest.raises(ValidationError, match="nights"):
        Proposal.model_validate(data)


def test_evidence_must_cite_a_listed_source() -> None:
    data = mock_data()["proposals"][0]
    data["flights"][0]["duration"]["evidence"][0]["source_id"] = 99

    with pytest.raises(ValidationError, match="listed source"):
        Proposal.model_validate(data)


def test_transfers_must_connect_the_cities() -> None:
    data = mock_data()["proposals"][1]
    data["intercity_transport"] = []

    with pytest.raises(ValidationError, match="Transfers"):
        Proposal.model_validate(data)


def test_shown_value_needs_evidence() -> None:
    with pytest.raises(ValidationError, match="evidence"):
        InfoField(value="Hotel", status="Estimated", evidence=[])


def test_hotel_price_cannot_be_sourced() -> None:
    data = mock_data()["proposals"][0]
    data["cities"][0]["hotel_price_per_night"]["status"] = "Sourced"

    with pytest.raises(ValidationError, match="live flight fare"):
        Proposal.model_validate(data)


def test_flight_price_can_be_sourced() -> None:
    data = mock_data()["proposals"][0]
    data["flights"][0]["price_per_person"]["status"] = "Sourced"

    assert Proposal.model_validate(data).flights[0].price_per_person.status == "Sourced"


def test_private_fields_are_not_part_of_a_proposal() -> None:
    data = mock_data()["proposals"][0]
    data["max_budget_sar"] = "3000"

    with pytest.raises(ValidationError, match="Extra inputs"):
        Proposal.model_validate(data)


@pytest.mark.parametrize(
    "text", ["Chosen for a budget of 2000", "ميزانية أحد الأعضاء", "One member asked"]
)
def test_adjustment_explanations_cannot_reveal_private_details(text: str) -> None:
    with pytest.raises(ValidationError, match="must not mention"):
        FlexibleAdjustment(category="flights", explanation=text)


def test_round_trip_must_share_one_link() -> None:
    data = mock_data()["proposals"][0]
    data["flights"][0]["legs"][1]["booking_url"] = "https://other.example/"

    with pytest.raises(ValidationError, match="one booking link"):
        Proposal.model_validate(data)


def test_split_total_cannot_be_sourced() -> None:
    data = mock_data()["proposals"][0]
    data["flights"][0]["trip_type"] = "split"
    data["flights"][0]["price_per_person"]["status"] = "Sourced"

    with pytest.raises(ValidationError, match="round_trip"):
        Proposal.model_validate(data)


def test_one_way_has_one_leg_and_cannot_be_within_budget() -> None:
    data = mock_data()["proposals"][0]
    data["flights"][0]["trip_type"] = "one_way"

    with pytest.raises(ValidationError, match="only an outbound"):
        Proposal.model_validate(data)

    data["flights"][0]["legs"].pop()
    data["budget_status"] = "within_group_budget"
    with pytest.raises(ValidationError, match="uncounted"):
        Proposal.model_validate(data)


def test_booking_links_must_be_https_or_null() -> None:
    data = mock_data()["proposals"][0]
    data["cities"][0]["booking_url"] = "http://booking.example/"

    with pytest.raises(ValidationError):
        Proposal.model_validate(data)
