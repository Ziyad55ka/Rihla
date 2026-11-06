from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.core.auth import CurrentIdentity
from app.schemas.activity_costs import ActivityCostSelections
from app.schemas.conflicts import GroupConflicts
from app.schemas.costs import ProposalCosts
from app.schemas.proposals import AirlineFareNote, Proposal
from app.services.airline_fares import fare_notes
from app.services.flight_booking_policy import complete_ground_route, single_booking
from app.services.flight_refresh import (
    FlightChecker,
    NoRoute,
    book_flight,
    refresh_flights,
    report_missing_flight,
)
from app.services.generation_errors import GenerationNeedsChanges, no_proposals_error
from app.services.generation_inputs import (
    FlightContext,
    GenerationInputsError,
    fetch_cost_context,
    fetch_flight_context,
    fetch_generation_inputs,
    save_flight_refresh,
)
from app.services.generation_precheck import generate_checked
from app.services.generation_progress import (
    GenerationProgress,
    ProgressReporter,
    read_progress,
)
from app.services.place_images import with_place_images
from app.services.proposal_costs import CostContext, proposal_costs
from app.services.proposal_generation import GenerationBlocked
from app.services.proposal_store import SupabaseProposalStore
from app.services.source_policy import apply_source_policy
from app.services.supabase import SupabaseHTTP
from app.services.trip_research import ResearchError
from app.services.trips import trip_rpc

router = APIRouter(prefix="/api/trips", tags=["proposals"])

RESEARCH_FAILURES = {
    "flight_source_unavailable": (
        503,
        "The flight source is temporarily unavailable. Try again later.",
    ),
    "departure_airport_unknown": (
        422,
        "A departure city could not be matched to an airport. "
        "Each member should check their departure city in preferences.",
    ),
    "search_quota": (503, "Today's search allowance has run out. Try again later."),
    "model_quota": (
        503,
        "The AI request limit has been reached. "
        "Retry timing depends on the service limit.",
    ),
    "generation_limit": (503, "The AI request limit was reached. Try again later."),
}
INPUT_FAILURES = {
    "access_denied": (403, "You do not have permission for this trip action."),
    "not_ready": (409, "Generation is waiting for all members to be ready."),
    "not_configured": (503, "Proposal generation is not set up on the backend."),
    "proposal_not_found": (404, "This proposal has been replaced."),
}


class FlightSummary(BaseModel):
    direction: Literal["outbound", "return"]
    airline: str | None
    flight_number: str | None
    departure_time: str | None
    arrival_time: str | None


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    regenerate: bool = False
    # The administrator's chosen trip length in days; None lets the AI choose.
    trip_days: int | None = Field(default=None, ge=1, le=60)


class Begun(BaseModel):
    started: bool
    version: int | None


class StoredProposals(BaseModel):
    version: int | None
    complete: bool
    generated_at: datetime | None
    generating: bool
    needs_regeneration: bool
    proposals: list[Proposal]
    # Set from the backend's settings, so the page has no copy of these numbers.
    price_fresh_hours: int = 3
    price_stale_hours: int = 24
    price_review_minutes: int = 15
    refresh_cooldown_minutes: int = 5
    # US-13: the caller's own cost breakdown for each proposal. Worked out on
    # reading and never saved. Empty when there are no proposals.
    costs: list[ProposalCosts] = []


class GeneratedProposals(StoredProposals):
    message: str | None
    reused: bool
    demo: bool


class FlightFacts(BaseModel):
    """What a check found. Never a passenger count or a budget."""

    url: str | None
    seller: str | None
    seller_type: str | None
    # Which source: "ignav" or "tripcom".
    provider: str | None
    exact_flight: bool
    price_sar: Decimal | None
    # Set only when the price differs from the one saved.
    previous_price_sar: Decimal | None
    cabin_class: str | None
    fare_name: str | None
    checked_bags: int | None
    carry_on_bags: int | None
    # Flight numbers and local times in the order shown, so a person can find it.
    flights: list[FlightSummary]
    airline_fares: list[AirlineFareNote]


class AlternativeResponse(FlightFacts):
    # gone: already saved in place of the old flight. The others are suggestions.
    reason: Literal["gone", "no_link", "cheaper", "agent"]
    # Null when not checked. Never says by how much.
    within_budget: bool | None


class FlightCheckResponse(FlightFacts):
    updated: bool
    # Set means url, if any, is a Google Flights search.
    fallback: (
        Literal["not_available", "limit", "demo", "check_failed", "no_link"] | None
    )
    alternative: AlternativeResponse | None
    # Google Flights with both chosen flights selected for the group, or null when a
    # flight detail is missing. Sellers and their round-trip totals are listed there.
    itinerary_url: str | None = None
    # With fallback "limit": when a new check is allowed again.
    retry_at: datetime | None = None
    now_over_budget: bool
    checked_at: datetime | None
    link_valid_minutes: int
    next_refresh_seconds: int


def _summaries(route) -> list[FlightSummary]:
    if route is None:
        return []
    return [
        FlightSummary(
            direction=item.direction,
            airline=item.airline.value,
            flight_number=item.flight_number,
            departure_time=item.departure_time,
            arrival_time=item.arrival_time,
        )
        for item in route.legs
    ]


def _check_response(result, settings) -> FlightCheckResponse:
    route = result.flights
    alternative = result.alternative
    return FlightCheckResponse(
        url=result.url,
        seller=result.seller,
        seller_type=result.seller_type,
        provider=result.provider,
        exact_flight=result.exact_flight,
        price_sar=result.price_sar,
        previous_price_sar=result.previous_price_sar,
        cabin_class=route.cabin_class if route else None,
        fare_name=route.fare_name if route else None,
        checked_bags=route.checked_bags if route else None,
        carry_on_bags=route.carry_on_bags if route else None,
        flights=_summaries(route),
        airline_fares=fare_notes(route) if route else [],
        updated=result.updated,
        fallback=result.fallback,
        alternative=AlternativeResponse(
            url=alternative.url,
            seller=alternative.seller,
            seller_type=alternative.flights.seller_type,
            provider=alternative.provider,
            exact_flight=alternative.exact_flight,
            price_sar=alternative.price_sar,
            previous_price_sar=None,
            cabin_class=alternative.flights.cabin_class,
            fare_name=alternative.flights.fare_name,
            checked_bags=alternative.flights.checked_bags,
            carry_on_bags=alternative.flights.carry_on_bags,
            flights=_summaries(alternative.flights),
            airline_fares=fare_notes(alternative.flights),
            reason=alternative.reason,
            within_budget=alternative.within_budget,
        )
        if alternative
        else None,
        itinerary_url=result.itinerary_url,
        retry_at=result.retry_at,
        now_over_budget=result.budget_status == "over_group_budget",
        checked_at=result.checked_at,
        link_valid_minutes=settings.link_valid_minutes,
        next_refresh_seconds=settings.refresh_cooldown_minutes * 60,
    )


async def _save_check(
    result, trip_id: UUID, proposal_id: UUID, identity, settings, required: bool
) -> None:
    if not result.updated or result.flights is None:
        return
    try:
        await save_flight_refresh(
            trip_id,
            proposal_id,
            identity.account.id,
            result.flights,
            result.budget_status,
            settings,
        )
    except GenerationInputsError as error:
        # A person about to book still needs the link, even if saving failed.
        if required:
            raise HTTPException(
                503, "Flight checks are temporarily unavailable."
            ) from error


def _with_fare_notes(proposal: Proposal) -> Proposal:
    return proposal.model_copy(
        update={
            "flights": [
                route.model_copy(update={"airline_fares": fare_notes(route)})
                for route in proposal.flights
            ]
        }
    )


async def _read(trip_id: UUID, identity, client, settings) -> StoredProposals:
    # Filtered by departure city inside the database, for every caller.
    stored = await trip_rpc(
        client,
        identity,
        "rihla_get_proposals",
        {"p_trip_id": str(trip_id)},
        StoredProposals,
    )
    proposals = await with_place_images(stored.proposals, settings)
    proposals = [
        _with_fare_notes(apply_source_policy(item, settings.booking_domains))
        for item in proposals
    ]
    context: CostContext | None = None
    activity_choices = {}
    if proposals:
        # Without the group context the page still gets this member's own costs.
        try:
            context = await fetch_cost_context(trip_id, identity.account.id, settings)
        except GenerationInputsError:
            context = None
        try:
            activity_data = await trip_rpc(
                client,
                identity,
                "rihla_get_activity_costs",
                {"p_trip_id": str(trip_id)},
                ActivityCostSelections,
            )
            activity_choices = {a.id: a for a in activity_data.proposals}
        except HTTPException:
            # Before the US-12 migration is applied, retain the explicit
            # "activities not included" state rather than inventing a zero.
            pass
    return stored.model_copy(
        update={
            "proposals": proposals,
            "needs_regeneration": stored.needs_regeneration
            or any(
                not single_booking(
                    route.trip_type, (leg.booking_url for leg in route.legs)
                )
                or not complete_ground_route(
                    (city.city for city in proposal.cities),
                    route.destination_airport,
                    route.return_airport,
                )
                for proposal in proposals
                for route in proposal.flights
            ),
            "costs": [
                proposal_costs(
                    item,
                    settings.meals_per_day_sar,
                    context,
                    activity_choices[item.id].activity_ids
                    if item.id in activity_choices
                    and (
                        activity_choices[item.id].has_selection is True
                        or (
                            activity_choices[item.id].has_selection is None
                            and activity_choices[item.id].activity_ids
                        )
                    )
                    else None,
                    activity_choices[item.id].group_cost
                    if item.id in activity_choices
                    else None,
                    activity_choices[item.id].saved_members
                    if item.id in activity_choices
                    else None,
                )
                for item in proposals
            ],
            "price_fresh_hours": settings.price_fresh_hours,
            "price_stale_hours": settings.price_stale_hours,
            "price_review_minutes": settings.price_review_minutes,
            "refresh_cooldown_minutes": settings.refresh_cooldown_minutes,
        }
    )


@router.get("/{trip_id}/conflicts", response_model=GroupConflicts)
async def read_conflicts(
    trip_id: UUID, identity: CurrentIdentity, client: SupabaseHTTP
):
    return await trip_rpc(
        client,
        identity,
        "rihla_get_group_conflicts",
        {"p_trip_id": str(trip_id)},
        GroupConflicts,
    )


@router.get("/{trip_id}/proposals/progress", response_model=GenerationProgress | None)
async def read_generation_progress(
    trip_id: UUID, identity: CurrentIdentity, client: SupabaseHTTP
):
    """What a running generation is doing, for any member of the trip.

    Holds no private data. Membership is checked with the same RPC as conflicts.
    """
    await trip_rpc(
        client,
        identity,
        "rihla_get_group_conflicts",
        {"p_trip_id": str(trip_id)},
        GroupConflicts,
    )
    return read_progress(str(trip_id))


@router.get("/{trip_id}/proposals", response_model=StoredProposals)
async def read_proposals(
    trip_id: UUID, request: Request, identity: CurrentIdentity, client: SupabaseHTTP
):
    return await _read(trip_id, identity, client, request.app.state.settings)


async def _flight_context(
    trip_id: UUID, proposal_id: UUID, identity, settings
) -> FlightContext:
    # Only the account verified by Supabase Auth is passed, never a request value.
    try:
        return await fetch_flight_context(
            trip_id, proposal_id, identity.account.id, settings
        )
    except GenerationInputsError as error:
        status, message = INPUT_FAILURES.get(
            error.code, (503, "Flight checks are temporarily unavailable.")
        )
        raise HTTPException(status, message) from error


@router.post(
    "/{trip_id}/proposals/{proposal_id}/book-flight",
    response_model=FlightCheckResponse,
)
async def book_proposal_flight(
    trip_id: UUID,
    proposal_id: UUID,
    request: Request,
    identity: CurrentIdentity,
    leg: Annotated[Literal["round_trip"], Query()],
):
    settings = request.app.state.settings
    context = await _flight_context(trip_id, proposal_id, identity, settings)
    try:
        result = await book_flight(
            FlightChecker(settings),
            context.proposal,
            context.city or "",
            leg,
            context.adults,
            str(trip_id),
            str(identity.account.id),
            context.ceiling,
        )
    except NoRoute as error:
        raise HTTPException(
            404, "No flights from your city in this proposal."
        ) from error
    await _save_check(result, trip_id, proposal_id, identity, settings, required=False)
    return _check_response(result, settings)


@router.post(
    "/{trip_id}/proposals/{proposal_id}/refresh-flights",
    response_model=FlightCheckResponse,
)
async def refresh_proposal_flights(
    trip_id: UUID,
    proposal_id: UUID,
    request: Request,
    identity: CurrentIdentity,
):
    settings = request.app.state.settings
    context = await _flight_context(trip_id, proposal_id, identity, settings)
    try:
        result = await refresh_flights(
            FlightChecker(settings),
            context.proposal,
            context.city or "",
            context.adults,
            context.ceiling,
            str(trip_id),
            str(identity.account.id),
        )
    except NoRoute as error:
        raise HTTPException(
            404, "No flights from your city in this proposal."
        ) from error
    await _save_check(result, trip_id, proposal_id, identity, settings, required=True)
    return _check_response(result, settings)


@router.post(
    "/{trip_id}/proposals/{proposal_id}/flight-not-offered",
    response_model=FlightCheckResponse,
)
async def flight_not_offered(
    trip_id: UUID,
    proposal_id: UUID,
    request: Request,
    identity: CurrentIdentity,
):
    """The member's seller page did not offer this flight. Find another one."""
    settings = request.app.state.settings
    context = await _flight_context(trip_id, proposal_id, identity, settings)
    try:
        result = await report_missing_flight(
            FlightChecker(settings),
            context.proposal,
            context.city or "",
            context.adults,
            context.ceiling,
            str(trip_id),
            str(identity.account.id),
        )
    except NoRoute as error:
        raise HTTPException(
            404, "No flights from your city in this proposal."
        ) from error
    await _save_check(result, trip_id, proposal_id, identity, settings, required=True)
    return _check_response(result, settings)


@router.post("/{trip_id}/proposals", response_model=GeneratedProposals)
async def generate_trip_proposals(
    trip_id: UUID,
    request: Request,
    identity: CurrentIdentity,
    client: SupabaseHTTP,
    body: GenerateRequest | None = None,
):
    settings = request.app.state.settings
    args = {"p_trip_id": str(trip_id)}
    # Rejects anyone but the administrator, before the secret key or any quota is used.
    begun = await trip_rpc(
        client, identity, "rihla_begin_proposal_generation", args, Begun
    )
    if not begun.started:
        raise HTTPException(409, "Proposals are already being generated for this trip.")
    progress = ProgressReporter(str(trip_id))
    try:
        conflicts = await trip_rpc(
            client, identity, "rihla_get_group_conflicts", args, GroupConflicts
        )
        if not conflicts.can_generate:
            raise GenerationBlocked(*conflicts.conflicts)
        # Only the account verified by Supabase Auth is passed, never a request value.
        generation = await fetch_generation_inputs(
            trip_id, identity.account.id, settings
        )
        if body and body.trip_days:
            if body.trip_days > generation.shared_days:
                raise HTTPException(
                    422, "The trip is longer than the group's shared dates."
                )
            generation = generation.model_copy(update={"trip_days": body.trip_days})
        result = await generate_checked(
            generation,
            settings,
            store=SupabaseProposalStore(client, identity, settings, begun.version),
            version=begun.version,
            regenerate=body.regenerate if body else False,
            progress=progress,
        )
        progress.stage("done")
    except GenerationNeedsChanges as needs:
        progress.stage("failed")
        raise HTTPException(409, needs.detail()) from needs
    except GenerationBlocked as blocked:
        progress.stage("failed")
        detail = {
            "message": " ".join(blocked.messages),
            "categories": blocked.categories,
        }
        if blocked.categories == ["budget"]:
            detail.update(
                {
                    "code": "budget_limit",
                    "suggestions": [
                        {
                            "action": action,
                            "kind": "review_budget",
                            "text": "Try fewer nights or more affordable destinations.",
                            "params": {},
                        }
                        for action in ("edit_dates", "edit_preferences")
                    ],
                }
            )
        raise HTTPException(
            409,
            detail,
        ) from blocked
    except GenerationInputsError as error:
        progress.stage("failed")
        status, message = INPUT_FAILURES.get(
            error.code, (503, "Proposal generation is temporarily unavailable.")
        )
        raise HTTPException(status, message) from error
    except ResearchError as error:
        progress.stage("failed")
        if error.code == "model_invalid_output":
            raise HTTPException(409, no_proposals_error().detail()) from error
        status, message = RESEARCH_FAILURES.get(
            error.code, (503, "Proposal generation is temporarily unavailable.")
        )
        retry_at = None
        if error.retry_after and error.retry_after.isdigit():
            retry_at = (
                datetime.now(UTC)
                + timedelta(seconds=min(int(error.retry_after), 172800))
            ).isoformat()
        raise HTTPException(
            status,
            {
                "code": error.code,
                "message": message,
                "suggestions": [
                    {
                        "action": "edit_preferences"
                        if error.code == "departure_airport_unknown"
                        else "retry",
                        "kind": "check_departure_city"
                        if error.code == "departure_airport_unknown"
                        else "retry_after"
                        if retry_at
                        else "wait_and_retry",
                        "text": message
                        if error.code == "departure_airport_unknown"
                        else "Wait a few minutes, then generate again.",
                        "params": {"retry_at": retry_at} if retry_at else {},
                    }
                ],
            },
            headers={"Retry-After": error.retry_after} if retry_at else None,
        ) from error
    finally:
        await trip_rpc(client, identity, "rihla_end_proposal_generation", args, dict)

    stored = await _read(trip_id, identity, client, settings)
    return GeneratedProposals(
        **stored.model_dump(),
        message=result.message,
        reused=result.reused,
        demo=result.demo,
    )
