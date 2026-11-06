"""US-12-AC03: combine saved activity choices with the caller's proposal costs.

The route must supply the member-filtered proposal, never all members' flights.
Room and transfer assumptions match the existing proposal generation baseline:
one hotel room per person; transfer prices are already per person. This small
service does not recalculate private group budgets. The daily allowance matches
the main cost page, so choosing activities cannot make that cost disappear.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from app.schemas.activity_estimate import ActivityProposalEstimate, EstimateComponent
from app.schemas.proposals import Activity, CityStay, Proposal, SarPrice
from app.services.hotel_nights import hotel_nights


def activity_date_fits(proposal: Proposal, stay: CityStay, activity: Activity) -> bool:
    """Dated events must fit the city stay and the member's usable flight dates."""
    if activity.scheduled_date.value is None:
        return True
    try:
        day = date.fromisoformat(activity.scheduled_date.value)
    except ValueError:
        return False
    start = proposal.start_date + timedelta(
        days=sum(c.nights for c in proposal.cities if c.order < stay.order)
    )
    end = min(proposal.end_date, start + timedelta(days=stay.nights))
    for route in proposal.flights:
        for leg in route.legs:
            try:
                clock = datetime.fromisoformat(
                    (
                        leg.arrival_time
                        if leg.direction == "outbound"
                        else leg.departure_time
                    )
                    or ""
                )
            except ValueError:
                continue
            if leg.direction == "outbound":
                start = max(start, clock.date())
            elif clock.hour < 12:
                end = min(end, clock.date() - timedelta(days=1))
    return start <= day <= end


def proposal_estimate(
    proposal: Proposal,
    activity_ids: list[UUID],
    meals_per_day_sar: Decimal = Decimal(150),
) -> ActivityProposalEstimate:
    selected = set(activity_ids)
    known = {a.id for stay in proposal.cities for a in stay.activities}
    if len(selected) != len(activity_ids) or not selected <= known:
        raise ValueError("Select valid activities from this proposal.")

    def component(items: list[tuple[SarPrice, int]]) -> EstimateComponent:
        result = EstimateComponent()
        for price, quantity in items:
            if quantity == 0:
                continue
            if price.amount_sar is None:
                result.missing_items += 1
                continue
            result.known_amount_sar += price.amount_sar * quantity
            result.unconfirmed_items += price.status == "Unconfirmed"
            result.estimated_items += price.status == "Estimated"
        result.known_amount_sar = result.known_amount_sar.quantize(Decimal("0.01"))
        return result

    if len(proposal.flights) > 1:
        raise ValueError("Estimate requires a member-filtered proposal.")
    flights = component([(route.price_per_person, 1) for route in proposal.flights])
    # Missing flight routes or one-way fares leave a return cost uncounted.
    if not proposal.flights:
        flights.missing_items += 1
    elif proposal.flights[0].trip_type == "one_way":
        flights.missing_items += 1
    needed = hotel_nights(proposal.cities, proposal.flights, proposal.end_date)
    accommodation = component(
        [
            (stay.hotel_price_per_night, nights)
            for stay, nights in zip(proposal.cities, needed, strict=True)
        ]
    )
    transport = component(
        [(leg.price_per_person, 1) for leg in proposal.intercity_transport]
    )
    activities = component(
        [
            (activity.price_per_person, 1)
            for stay in proposal.cities
            for activity in stay.activities
            if activity.id in selected
        ]
    )
    if not meals_per_day_sar.is_finite() or meals_per_day_sar < 0:
        raise ValueError("Invalid daily allowance.")
    days = (proposal.end_date - proposal.start_date).days + 1
    meals = EstimateComponent(
        known_amount_sar=(meals_per_day_sar * days).quantize(Decimal("0.01")),
        unconfirmed_items=1 if meals_per_day_sar else 0,
    )
    parts = [flights, accommodation, transport, meals, activities]
    total = EstimateComponent(
        known_amount_sar=sum((p.known_amount_sar for p in parts), Decimal("0.00")),
        missing_items=sum(p.missing_items for p in parts),
        unconfirmed_items=sum(p.unconfirmed_items for p in parts),
        estimated_items=sum(p.estimated_items for p in parts),
    )
    return ActivityProposalEstimate(
        proposal_id=proposal.id,
        version=proposal.version,
        flights=flights,
        accommodation=accommodation,
        transport=transport,
        meals=meals,
        activities=activities,
        total=total,
    )
