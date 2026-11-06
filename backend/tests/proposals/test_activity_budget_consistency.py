"""Saved selection, group aggregate and cost tables must agree. No live services."""

import asyncio
from decimal import Decimal
from uuid import UUID

from app.schemas.costs import CostAmount
from app.schemas.proposals import SarPrice
from app.services.activity_estimate import proposal_estimate
from app.services.proposal_costs import group_activity_cost, proposal_costs
from tests.proposals.test_costs_and_compatibility import context, line, scenario
from tests.test_activity_estimate import example

MEMBERS = [UUID(f"00000000-0000-4000-8000-{index:012d}") for index in range(1, 4)]


def trip():
    proposal = example()
    proposal.activity_allowance_per_person = SarPrice(
        amount_sar="675", status="Unconfirmed", evidence=[]
    )
    proposal.cities[0].activities[0].price_per_person = SarPrice(
        amount_sar="335", status="Unconfirmed", evidence=[]
    )
    return proposal


def test_saved_activity_335_replaces_reserve_675_in_every_person_and_group_total():
    proposal = trip()
    ids = [proposal.cities[0].activities[0].id]
    private = context(members=1)
    # Context references the same proposal and route as the member sees.
    private.proposals[0].id = proposal.id
    costs = scenario(proposal_costs(proposal, Decimal(150), private, ids), "single")
    estimate = proposal_estimate(proposal, ids)
    assert line(costs, "activities").per_person.amount_sar == Decimal(335)
    assert estimate.activities.known_amount_sar == Decimal(335)
    assert costs.group_total.amount_sar == costs.per_person_total.amount_sar
    assert costs.per_person_total.amount_sar == estimate.total.known_amount_sar


def test_group_keeps_reserve_only_for_members_who_have_not_saved():
    proposal = trip()
    ids = [proposal.cities[0].activities[0].id]
    group = group_activity_cost(proposal, [ids, []], 3)
    assert group.amount_sar == Decimal(1010)  # 335 + intentional zero + unsaved 675
    private = context(members=3)
    private.proposals[0].id = proposal.id
    saved_total = group.model_copy(update={"amount_sar": Decimal(335)})
    costs = scenario(
        proposal_costs(proposal, Decimal(150), private, ids, saved_total, 2), "single"
    )
    own_base = costs.per_person_total.amount_sar - Decimal(335)
    assert costs.group_total.amount_sar == own_base * 3 + Decimal(1010)


def test_unknown_selected_prices_remain_partial_instead_of_free():
    proposal = trip()
    unknown = proposal.cities[0].activities[2]
    assert unknown.price_per_person.amount_sar is None
    group = group_activity_cost(proposal, [[unknown.id]], 1)
    assert group.amount_sar is None and group.partial


def test_all_members_saved_including_zero_choice_have_no_remaining_reserve():
    proposal = trip()
    private = context(members=2)
    private.proposals[0].id = proposal.id
    costs = scenario(
        proposal_costs(
            proposal,
            Decimal(150),
            private,
            [],
            CostAmount(amount_sar=Decimal(335), status="Unconfirmed"),
            2,
        ),
        "single",
    )
    assert line(costs, "activities").per_person.amount_sar == 0
    assert (
        costs.group_total.amount_sar
        == costs.per_person_total.amount_sar * 2 + Decimal(335)
    )


def test_unsaved_caller_keeps_their_reserve_without_losing_others_choices():
    proposal = trip()
    private = context(members=2)
    private.proposals[0].id = proposal.id
    costs = scenario(
        proposal_costs(
            proposal,
            Decimal(150),
            private,
            None,
            CostAmount(amount_sar=Decimal(335), status="Unconfirmed"),
            1,
        ),
        "single",
    )
    assert line(costs, "activities").per_person.amount_sar == 675
    base = costs.per_person_total.amount_sar - Decimal(675)
    assert costs.group_total.amount_sar == base * 2 + Decimal(1010)


def test_researched_admission_is_normalized_before_storage_and_costing(monkeypatch):
    from app.core.config import Settings
    from app.services import activity_research

    proposal = trip()
    proposal.cities[0].city = "Istanbul"
    attraction = proposal.cities[0].activities[0]
    attraction.name = attraction.name.model_copy(update={"value": "Topkapi Palace"})
    attraction.price_per_person = SarPrice(
        amount_sar="150", status="Unconfirmed", evidence=[]
    )

    async def researched(*args):
        return proposal

    monkeypatch.setattr(activity_research, "_find_activities", researched)
    stored = asyncio.run(
        activity_research.find_activities(proposal, Settings(_env_file=None))
    )
    assert stored.cities[0].activities[0].price_per_person.amount_sar == Decimal(210)
    assert proposal_estimate(
        stored, [attraction.id]
    ).activities.known_amount_sar == Decimal(210)
