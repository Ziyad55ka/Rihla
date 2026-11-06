from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from app.api.routes.proposals import StoredProposals
from app.core.auth import CurrentIdentity
from app.core.proposal_settings import DEFAULT_BOOKING_DOMAINS
from app.schemas.activities import ActivitySelections, SelectionRequest
from app.services.activity_estimate import activity_date_fits, proposal_estimate
from app.services.generation_inputs import GenerationInputsError, fetch_flight_context
from app.services.proposal_generation import OptionRejected, budget_status
from app.services.source_policy import apply_source_policy
from app.services.supabase import SupabaseHTTP
from app.services.trips import trip_rpc

router = APIRouter(prefix="/api/trips", tags=["activities"])


async def with_estimate(
    selection,
    trip_id,
    identity,
    client,
    booking_domains=None,
    meals_per_day_sar=Decimal(150),
    require_current=False,
):
    # The database filters flight routes and sources for the authenticated member.
    stored = await trip_rpc(
        client,
        identity,
        "rihla_get_proposals",
        {
            "p_trip_id": str(trip_id),
        },
        StoredProposals,
    )
    if require_current and stored.needs_regeneration:
        raise HTTPException(
            409, "This proposal changed. Reload before saving activities."
        )
    proposal = next(
        (p for p in stored.proposals if p.id == selection.proposal_id), None
    )
    if proposal is None or proposal.version != selection.version:
        raise HTTPException(
            409, "This proposal changed. Reload before saving activities."
        )
    proposal = apply_source_policy(
        proposal,
        booking_domains
        if booking_domains is not None
        else list(DEFAULT_BOOKING_DOMAINS),
    )
    known = {a.id for stay in proposal.cities for a in stay.activities}
    if not set(selection.activity_ids) <= known:
        raise HTTPException(422, "Select valid activities from this proposal.")
    if require_current and any(
        a.id in selection.activity_ids and not activity_date_fits(proposal, stay, a)
        for stay in proposal.cities
        for a in stay.activities
    ):
        raise HTTPException(422, "Select valid activities from this proposal.")
    try:
        estimate = proposal_estimate(
            proposal, selection.activity_ids, meals_per_day_sar
        )
    except ValueError as error:
        raise HTTPException(
            503, "Proposal costs are unavailable. Try again later."
        ) from error
    return selection.model_copy(update={"estimate": estimate})


@router.get(
    "/{trip_id}/proposals/{proposal_id}/activities/selection",
    response_model=ActivitySelections,
)
async def read_selection(
    trip_id: UUID,
    proposal_id: UUID,
    identity: CurrentIdentity,
    client: SupabaseHTTP,
    request: Request,
):
    selection = await trip_rpc(
        client,
        identity,
        "rihla_get_activity_selection",
        {
            "p_trip_id": str(trip_id),
            "p_proposal_id": str(proposal_id),
        },
        ActivitySelections,
    )
    return await with_estimate(
        selection,
        trip_id,
        identity,
        client,
        request.app.state.settings.booking_domains,
        request.app.state.settings.meals_per_day_sar,
    )


@router.put(
    "/{trip_id}/proposals/{proposal_id}/activities/selection",
    response_model=ActivitySelections,
)
async def save_selection(
    trip_id: UUID,
    proposal_id: UUID,
    body: SelectionRequest,
    identity: CurrentIdentity,
    client: SupabaseHTTP,
    request: Request,
):
    # Calculate before writing: a failed estimate must not report failure after
    # the choices have already been saved. The RPC still checks the version.
    prepared = await with_estimate(
        ActivitySelections(**body.model_dump(), proposal_id=proposal_id),
        trip_id,
        identity,
        client,
        request.app.state.settings.booking_domains,
        request.app.state.settings.meals_per_day_sar,
        require_current=True,
    )
    # The browser's proposal contains only this member's route. Check the
    # costliest group route and private minimum budget before any write.
    settings = request.app.state.settings
    try:
        context = await fetch_flight_context(
            trip_id, proposal_id, identity.account.id, settings
        )
        full = apply_source_policy(context.proposal, settings.booking_domains)
        if full.version != body.version:
            raise HTTPException(
                409, "This proposal changed. Reload before saving activities."
            )
        selected = set(body.activity_ids)
        activity_cost = sum(
            (a.price_per_person.amount_sar or Decimal(0))
            for stay in full.cities
            for a in stay.activities
            if a.id in selected
        )
        days = (full.end_date - full.start_date).days + 1
        budget_status(
            full.cities,
            full.flights,
            full.intercity_transport,
            context.ceiling,
            settings.meals_per_day_sar * days + activity_cost,
        )
    except OptionRejected as error:
        raise HTTPException(
            422,
            "These activities exceed the group's budget. "
            "Choose fewer or less expensive activities.",
        ) from error
    except GenerationInputsError as error:
        raise HTTPException(
            503,
            "We couldn’t verify the group budget. Try again before saving activities.",
        ) from error
    selection = await trip_rpc(
        client,
        identity,
        "rihla_set_activity_selection",
        {
            "p_trip_id": str(trip_id),
            "p_proposal_id": str(proposal_id),
            "p_version": body.version,
            "p_activity_ids": [str(item) for item in body.activity_ids],
        },
        ActivitySelections,
    )
    return selection.model_copy(update={"estimate": prepared.estimate})
