from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

from app.core.auth import CurrentIdentity
from app.schemas.planning import GroupConflicts
from app.schemas.proposals import Proposal
from app.services.flight_refresh import (
    BookLeg,
    FlightChecker,
    NoRoute,
    book_flight,
    refresh_flights,
)
from app.services.generation_inputs import (
    FlightContext,
    FlightGroup,
    GenerationInputsError,
    fetch_flight_context,
    fetch_flight_group,
    fetch_generation_inputs,
    save_flight_refresh,
)
from app.services.generation_precheck import generate_checked
from app.services.proposal_generation import GenerationBlocked
from app.services.proposal_store import SupabaseProposalStore
from app.services.source_policy import apply_source_policy
from app.services.supabase import SupabaseHTTP
from app.services.trip_research import ResearchError
from app.services.trips import trip_rpc

router = APIRouter(prefix="/api/trips", tags=["proposals"])

RESEARCH_FAILURES = {
    "search_quota": (503, "Today's search allowance has run out. Try again later."),
    "model_quota": (503, "Today's AI allowance has run out. Try again later."),
    "generation_limit": (503, "The AI request limit was reached. Try again later."),
}
INPUT_FAILURES = {
    "access_denied": (403, "You do not have permission for this trip action."),
    "not_ready": (409, "Generation is waiting for all members to be ready."),
    "not_configured": (503, "Proposal generation is not set up on the backend."),
    "proposal_not_found": (404, "This proposal has been replaced."),
}


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    regenerate: bool = False


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
    # Worked out by the backend. Never a count or a list of cities.
    all_same_city: bool = False
    # Set from the backend's settings, so the page has no copy of these numbers.
    price_fresh_hours: int = 3
    price_stale_hours: int = 24
    refresh_cooldown_minutes: int = 5


class GeneratedProposals(StoredProposals):
    message: str | None
    reused: bool
    demo: bool


class BookFlightResponse(BaseModel):
    url: str
    # not_available or limit or demo mean url is a Google Flights search.
    fallback: Literal["not_available", "limit", "demo"] | None
    seller: str | None
    exact_flight: bool
    price_sar: Decimal | None
    # Set only when the price differs from the one saved.
    previous_price_sar: Decimal | None


class RefreshFlightsResponse(BaseModel):
    updated: bool
    fallback: Literal["not_available", "limit", "demo"] | None
    # A Google Flights search, for when no update was possible.
    url: str | None
    now_over_budget: bool
    next_refresh_seconds: int


def _with_group_totals(proposal: Proposal, group: FlightGroup) -> Proposal:
    """Only for a whole trip from one city. Other trips get no group figure or count."""
    if not group.all_same_city or group.members <= 1:
        return proposal
    return proposal.model_copy(
        update={
            "flights": [
                route.model_copy(
                    update={
                        "group_total_sar": (
                            route.price_per_person.amount_sar * group.members
                        ).quantize(Decimal("0.01"))
                    }
                )
                if route.price_per_person.amount_sar
                else route
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
    group = FlightGroup()
    if stored.proposals:
        # A failed check only hides the group figure, never the proposals.
        try:
            group = await fetch_flight_group(trip_id, identity.account.id, settings)
        except GenerationInputsError:
            pass
    return stored.model_copy(
        update={
            "proposals": [
                _with_group_totals(
                    apply_source_policy(item, settings.booking_domains), group
                )
                for item in stored.proposals
            ],
            "all_same_city": group.all_same_city,
            "price_fresh_hours": settings.price_fresh_hours,
            "price_stale_hours": settings.price_stale_hours,
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


@router.get(
    "/{trip_id}/proposals/{proposal_id}/book-flight",
    response_model=BookFlightResponse,
)
async def book_proposal_flight(
    trip_id: UUID,
    proposal_id: UUID,
    request: Request,
    identity: CurrentIdentity,
    leg: Annotated[BookLeg, Query()],
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
        )
    except NoRoute as error:
        raise HTTPException(
            404, "No flights from your city in this proposal."
        ) from error
    return BookFlightResponse(
        url=result.url,
        fallback=result.fallback,
        seller=result.seller,
        exact_flight=result.exact_flight,
        price_sar=result.price_sar,
        previous_price_sar=result.previous_price_sar,
    )


@router.post(
    "/{trip_id}/proposals/{proposal_id}/refresh-flights",
    response_model=RefreshFlightsResponse,
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
    if result.updated:
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
            raise HTTPException(
                503, "Flight checks are temporarily unavailable."
            ) from error
    return RefreshFlightsResponse(
        updated=result.updated and result.fallback is None,
        fallback=result.fallback,
        url=result.url if result.fallback else None,
        now_over_budget=result.budget_status == "over_group_budget",
        next_refresh_seconds=settings.refresh_cooldown_minutes * 60,
    )


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
        result = await generate_checked(
            generation,
            settings,
            store=SupabaseProposalStore(client, identity, settings, begun.version),
            version=begun.version,
            regenerate=body.regenerate if body else False,
        )
    except GenerationBlocked as blocked:
        raise HTTPException(
            409,
            {"message": " ".join(blocked.messages), "categories": blocked.categories},
        ) from blocked
    except GenerationInputsError as error:
        status, message = INPUT_FAILURES.get(
            error.code, (503, "Proposal generation is temporarily unavailable.")
        )
        raise HTTPException(status, message) from error
    except ResearchError as error:
        status, message = RESEARCH_FAILURES.get(
            error.code, (503, "Proposal generation is temporarily unavailable.")
        )
        raise HTTPException(status, message) from error
    finally:
        await trip_rpc(client, identity, "rihla_end_proposal_generation", args, dict)

    stored = await _read(trip_id, identity, client, settings)
    return GeneratedProposals(
        **stored.model_dump(),
        message=result.message,
        reused=result.reused,
        demo=result.demo,
    )
