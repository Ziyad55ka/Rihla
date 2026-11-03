from decimal import Decimal
from uuid import UUID

import pytest
from activity_fixture import mock_data

from app.schemas.proposals import Proposal
from app.services.activity_estimate import proposal_estimate


def example():
    return Proposal.model_validate(mock_data()["proposals"][0])


def test_saved_choices_update_relevant_proposal_estimate_and_can_be_removed():
    proposal = example()
    museum, walk, event, restaurant = proposal.cities[0].activities
    assert proposal_estimate(proposal, []).total.known_amount_sar == Decimal("3000.00")
    selected = proposal_estimate(proposal, [museum.id, restaurant.id])
    assert selected.activities.known_amount_sar == Decimal("150.50")
    assert selected.total.known_amount_sar == Decimal("3150.50")
    assert selected.flights.known_amount_sar == Decimal("1200.00")
    assert selected.accommodation.known_amount_sar == Decimal("1800.00")
    assert proposal_estimate(
        proposal, [restaurant.id]
    ).total.known_amount_sar == Decimal("3065.00")
    assert proposal_estimate(proposal, [walk.id]).activities.known_amount_sar == 0
    assert proposal_estimate(proposal, [event.id]).activities.missing_items == 1
    assert proposal_estimate(proposal, []).activities.missing_items == 0


def test_missing_prices_and_return_costs_are_explicit_not_free():
    proposal = example()
    proposal.flights = []
    estimate = proposal_estimate(proposal, [])
    assert estimate.flights.missing_items == 1
    assert estimate.total.known_amount_sar == Decimal("1800.00")
    proposal = example()
    proposal.flights[0].trip_type = "one_way"
    assert proposal_estimate(proposal, []).flights.missing_items == 1


def test_estimate_refuses_other_members_flights_and_invalid_selections():
    proposal = example()
    route = proposal.flights[0].model_copy(update={"origin": "Other city"})
    proposal.flights.append(route)
    with pytest.raises(ValueError, match="member-filtered"):
        proposal_estimate(proposal, [])
    proposal = example()
    with pytest.raises(ValueError, match="valid activities"):
        proposal_estimate(proposal, [UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")])


def test_multi_city_hotel_nights_and_transfers_are_counted_once():
    proposal = Proposal.model_validate(mock_data()["proposals"][1])
    proposal.flights = proposal.flights[:1]
    result = proposal_estimate(proposal, [])
    hotel = sum(
        (s.hotel_price_per_night.amount_sar or 0) * s.nights for s in proposal.cities
    )
    transport = sum(
        s.price_per_person.amount_sar or 0 for s in proposal.intercity_transport
    )
    assert result.accommodation.known_amount_sar == hotel
    assert result.transport.known_amount_sar == transport
    ids = [s.activities[-1].id for s in proposal.cities]
    assert proposal_estimate(
        proposal, ids
    ).total.known_amount_sar == result.total.known_amount_sar + Decimal("130.00")


def test_estimate_is_recalculated_when_prices_change_and_preserves_trust_counts():
    proposal = example()
    activity = proposal.cities[0].activities[-1]
    original = proposal_estimate(proposal, [activity.id])
    activity.price_per_person.amount_sar = Decimal("75.25")
    updated = proposal_estimate(proposal, [activity.id])
    assert updated.total.known_amount_sar - original.total.known_amount_sar == Decimal(
        "10.25"
    )
    assert updated.activities.unconfirmed_items == 1
    assert updated.accommodation.estimated_items == 1
