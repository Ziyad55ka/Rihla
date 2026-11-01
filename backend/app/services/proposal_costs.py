"""US-13: one member's cost breakdown for a proposal, and the group's total.

Pure functions, so every figure can be tested without a network. The proposal
passed in is the member's own view (only their departure city's flights). The
group context comes from the backend's secret key and never reaches a browser:
only the totals worked out from it do.

The page shows two room plans. single matches budget_status in
proposal_generation: one person per room, so it errs high. shared puts two people
in each room and splits the cost evenly.
"""

import math
from collections.abc import Iterable
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.costs import (
    Assumption,
    CostAmount,
    CostLine,
    CostScenario,
    OwnBudget,
    ProposalCosts,
    RoomPlan,
)
from app.schemas.proposals import PriceStatus, Proposal, SarPrice

CENT = Decimal("0.01")
# Strongest first. A total takes the weakest status of its parts.
STRENGTH: tuple[PriceStatus, ...] = (
    "Sourced",
    "Estimated",
    "Unconfirmed",
    "Not available",
)
CORE = {"flights", "accommodation", "transport"}


class RoutePrice(BaseModel):
    """Only what the group total needs from one departure city's flights."""

    model_config = ConfigDict(extra="ignore")
    origin: str
    price_per_person: SarPrice


class ProposalRoutes(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: UUID
    flights: list[RoutePrice] = []


class OriginCount(BaseModel):
    origin: str
    members: int = Field(ge=1)


class CostContext(BaseModel):
    """Private to the backend. Never return it, log it or put it in an error."""

    member_count: int = Field(ge=1)
    own_budget_sar: Decimal | None
    origins: list[OriginCount]
    proposals: list[ProposalRoutes]


def _cents(value: Decimal) -> Decimal:
    return value.quantize(CENT)


def _weakest(statuses: Iterable[PriceStatus]) -> PriceStatus:
    return max(statuses, key=STRENGTH.index, default="Not available")


def _amount(parts: list[tuple[SarPrice, Decimal]]) -> CostAmount:
    """Adds price × multiplier for each part. Unknown parts make it partial."""
    known = [
        (price, times)
        for price, times in parts
        if price.status != "Not available" and price.amount_sar is not None
    ]
    if not known:
        return CostAmount(amount_sar=None, status="Not available", partial=bool(parts))
    return CostAmount(
        amount_sar=_cents(
            sum((price.amount_sar * times for price, times in known), Decimal(0))
        ),
        status=_weakest(price.status for price, _ in known),
        partial=len(known) < len(parts),
    )


def _sum(amounts: list[CostAmount]) -> CostAmount:
    known = [item for item in amounts if item.amount_sar is not None]
    if not known:
        return CostAmount(amount_sar=None, status="Not available", partial=True)
    return CostAmount(
        amount_sar=_cents(sum((item.amount_sar for item in known), Decimal(0))),
        status=_weakest(item.status for item in known),
        partial=len(known) < len(amounts) or any(item.partial for item in known),
    )


def _times(amount: CostAmount, factor: Decimal) -> CostAmount:
    if amount.amount_sar is None:
        return amount
    return amount.model_copy(update={"amount_sar": _cents(amount.amount_sar * factor)})


def _meals(days: int, per_day: Decimal) -> SarPrice | None:
    if per_day <= 0:
        return None
    # A general allowance with no source: Unconfirmed, never Estimated.
    return SarPrice(
        amount_sar=_cents(per_day * days), status="Unconfirmed", evidence=[]
    )


def _own_budget(
    total: CostAmount, lines: list[CostLine], budget: Decimal | None
) -> tuple[OwnBudget, Decimal | None]:
    if budget is None or total.amount_sar is None:
        return "unknown", None
    if total.amount_sar > budget:
        return "over", _cents(total.amount_sar - budget)
    uncertain = any(
        line.per_person.partial
        or line.per_person.status in {"Unconfirmed", "Not available"}
        for line in lines
        if line.category in CORE
    )
    return ("unconfirmed" if uncertain else "within"), None


def _group_flights(proposal_id: UUID, context: CostContext) -> CostAmount:
    routes = next((item for item in context.proposals if item.id == proposal_id), None)
    by_origin = {
        route.origin.strip().casefold(): route.price_per_person
        for route in (routes.flights if routes else [])
    }
    parts: list[tuple[SarPrice, Decimal]] = []
    for origin in context.origins:
        price = by_origin.get(origin.origin.strip().casefold())
        if price is None:
            price = SarPrice(amount_sar=None, status="Not available", evidence=[])
        parts.append((price, Decimal(origin.members)))
    return _amount(parts)


def _scenario(
    rooms: RoomPlan,
    proposal: Proposal,
    days: int,
    meals_per_day: Decimal,
    context: CostContext | None,
) -> CostScenario:
    members = context.member_count if context else 1
    # Shared rooms: two people per room, so a group needs half as many, rounded up.
    room_share = (
        Decimal(math.ceil(members / 2)) / Decimal(members)
        if rooms == "shared"
        else Decimal(1)
    )
    own_route = proposal.flights[0] if proposal.flights else None
    flights = _amount(
        [(own_route.price_per_person, Decimal(1))]
        if own_route
        else [
            (SarPrice(amount_sar=None, status="Not available", evidence=[]), Decimal(1))
        ]
    )
    stays = [
        (stay.hotel_price_per_night, Decimal(stay.nights))
        for stay in proposal.cities
        if stay.nights
    ]
    accommodation = _times(_amount(stays), room_share) if stays else None
    transport = (
        _amount(
            [(leg.price_per_person, Decimal(1)) for leg in proposal.intercity_transport]
        )
        if proposal.intercity_transport
        else None
    )
    meal_price = _meals(days, meals_per_day)
    meals = _amount([(meal_price, Decimal(1))]) if meal_price else None

    lines = [CostLine(category="flights", per_person=flights)]
    if accommodation:
        lines.append(CostLine(category="accommodation", per_person=accommodation))
    if transport:
        lines.append(CostLine(category="transport", per_person=transport))
    # Activities belong to US-11/12. Shown so the member knows they are not added yet.
    lines.append(
        CostLine(
            category="activities",
            per_person=CostAmount(amount_sar=None, status="Not available"),
            counted=False,
        )
    )
    if meals:
        lines.append(CostLine(category="meals", per_person=meals))

    counted = [line.per_person for line in lines if line.counted]
    total = _sum(counted)
    group: CostAmount | None = None
    if context:
        everyone = Decimal(members)
        shared_parts = [
            line.per_person
            for line in lines
            if line.counted and line.category != "flights"
        ]
        group = _sum(
            [
                _group_flights(proposal.id, context),
                *(_times(part, everyone) for part in shared_parts),
            ]
        )
    budget, over_by = _own_budget(
        total, lines, context.own_budget_sar if context else None
    )
    return CostScenario(
        rooms=rooms,
        lines=lines,
        per_person_total=total,
        group_total=group,
        own_budget=budget,
        over_by_sar=over_by,
    )


def proposal_costs(
    proposal: Proposal, meals_per_day: Decimal, context: CostContext | None
) -> ProposalCosts:
    days = (proposal.end_date - proposal.start_date).days + 1
    nights = sum(stay.nights for stay in proposal.cities)
    scenarios = [_scenario("single", proposal, days, meals_per_day, context)]
    if context and context.member_count > 1 and nights:
        scenarios.append(_scenario("shared", proposal, days, meals_per_day, context))

    own_route = proposal.flights[0] if proposal.flights else None
    assumptions: list[Assumption] = []
    if own_route is None:
        assumptions.append("flights_missing")
    else:
        assumptions.append("flights_own_city")
        if own_route.trip_type == "one_way":
            assumptions.append("flights_one_way")
    assumptions.append("rooms_single")
    if len(scenarios) > 1:
        assumptions.append("rooms_shared")
    if meals_per_day > 0:
        assumptions.append("meals_allowance")
    assumptions.append("activities_not_included")
    assumptions.append(
        "group_total_all_cities" if context else "group_total_unavailable"
    )
    assumptions.append("prices_may_change")
    return ProposalCosts(
        proposal_id=proposal.id,
        days=days,
        nights=nights,
        scenarios=scenarios,
        assumptions=assumptions,
    )
