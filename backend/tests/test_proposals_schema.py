import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.proposals import (
    FlexibleAdjustment,
    InfoField,
    Proposal,
    ProposalSet,
    SarPrice,
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


def test_price_cannot_be_confirmed() -> None:
    with pytest.raises(ValidationError):
        SarPrice(
            amount_sar="100",
            status="Sourced",
            evidence=[{"source_id": 1, "quote": "SAR 100"}],
        )


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
