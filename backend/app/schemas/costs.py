"""US-13: the cost breakdown a member sees for one proposal.

Worked out on reading, for the signed-in member, and never saved. It holds that
member's own costs and the group's total, but never another member's budget or
departure city. Other copy: frontend/src/types/proposal.ts.
"""

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.proposals import PriceStatus, StrictModel

CostCategory = Literal["flights", "accommodation", "transport", "activities", "meals"]
# single: one person per room, as the group budget check assumes.
# shared: two people per room, the cost split evenly.
RoomPlan = Literal["single", "shared"]
# Only the member's own budget, and only this label: never the amount.
# within: fits, and the main prices have evidence.
# over: more than the member's budget.
# unconfirmed: fits on the known prices, but one is uncertain or missing.
# unknown: the member has no saved budget, or it could not be read.
OwnBudget = Literal["within", "over", "unconfirmed", "unknown"]
# Codes the page turns into sentences, in both languages.
Assumption = Literal[
    "rooms_single",
    "rooms_shared",
    "flights_own_city",
    "flights_one_way",
    "flights_missing",
    "meals_allowance",
    "activities_not_included",
    "activities_selected",
    "activities_allowance",
    "group_total_all_cities",
    "group_total_unavailable",
    "prices_may_change",
    "last_night_unused",
]


class CostAmount(StrictModel):
    # The sum of the known parts, or null when no part is known.
    amount_sar: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    # The weakest status among the known parts. Not available when none is known.
    status: PriceStatus
    # True when at least one part is Not available, so the amount is too low.
    partial: bool = False


class CostLine(StrictModel):
    category: CostCategory
    per_person: CostAmount
    # False for lines shown for information only, such as activities not added yet.
    counted: bool = True


class CostScenario(StrictModel):
    rooms: RoomPlan
    lines: list[CostLine]
    per_person_total: CostAmount
    # Null when the backend could not read the group, such as without its secret key.
    group_total: CostAmount | None
    own_budget: OwnBudget
    # Set only when own_budget is over: by how much, for this member alone.
    over_by_sar: Decimal | None = Field(default=None, gt=0, decimal_places=2)


class ProposalCosts(StrictModel):
    proposal_id: UUID
    days: int = Field(ge=1)
    nights: int = Field(ge=0)
    # single always. shared too when the trip has more than one member.
    scenarios: list[CostScenario] = Field(min_length=1, max_length=2)
    assumptions: list[Assumption]
