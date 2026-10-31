import json
from pathlib import Path

from app.core.config import Settings
from app.schemas.proposals import Proposal
from app.services.proposal_views import view_for_member

MOCK = Path(__file__).resolve().parents[2] / "docs/examples/proposals.mock.json"


def stored_proposal() -> Proposal:
    """A proposal with flights from two departure cities and a source for each."""
    data = json.loads(MOCK.read_text(encoding="utf-8"))["proposals"][0]
    jeddah = json.loads(json.dumps(data["flights"][0]))
    jeddah["origin"] = "Jeddah"
    jeddah["duration"]["evidence"][0]["source_id"] = 3
    jeddah["price_per_person"]["evidence"][0]["source_id"] = 3
    data["flights"].append(jeddah)
    data["sources"].append(
        {"id": 3, "title": "Jeddah flights", "url": "https://example.com/jeddah"}
    )
    return Proposal.model_validate(data)


def test_member_receives_only_their_own_city() -> None:
    body = view_for_member(stored_proposal(), " riyadh ").model_dump_json()

    assert "Riyadh" in body
    assert "Jeddah" not in body
    assert "jeddah" not in body


def test_unmatched_city_receives_no_flights() -> None:
    view = view_for_member(stored_proposal(), "Dammam")

    assert view.flights == []


def test_shared_sources_stay_for_other_fields() -> None:
    view = view_for_member(stored_proposal(), "Jeddah")

    assert {source.id for source in view.sources} == {1, 3}


def test_all_mode_shows_every_city_without_names_changing_the_schema() -> None:
    view = view_for_member(stored_proposal(), "Riyadh", "all")

    assert [route.origin for route in view.flights] == ["Riyadh", "Jeddah"]


def test_own_is_the_default_setting() -> None:
    assert Settings(_env_file=None).flight_visibility == "own"
