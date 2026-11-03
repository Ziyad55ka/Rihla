from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.api.routes.proposals import StoredProposals
from app.core.auth import CurrentIdentity
from app.schemas.activities import ActivitySelections, SelectionRequest
from app.services.activity_estimate import proposal_estimate
from app.services.supabase import SupabaseHTTP
from app.services.trips import trip_rpc

router = APIRouter(prefix="/api/trips", tags=["activities"])


async def with_estimate(selection, trip_id, identity, client):
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
    proposal = next(
        (p for p in stored.proposals if p.id == selection.proposal_id), None
    )
    if proposal is None or proposal.version != selection.version:
        raise HTTPException(
            409, "This proposal changed. Reload before saving activities."
        )
    known = {a.id for stay in proposal.cities for a in stay.activities}
    if not set(selection.activity_ids) <= known:
        raise HTTPException(422, "Select valid activities from this proposal.")
    try:
        estimate = proposal_estimate(proposal, selection.activity_ids)
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
    return await with_estimate(selection, trip_id, identity, client)


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
):
    # Calculate before writing: a failed estimate must not report failure after
    # the choices have already been saved. The RPC still checks the version.
    prepared = await with_estimate(
        ActivitySelections(**body.model_dump(), proposal_id=proposal_id),
        trip_id,
        identity,
        client,
    )
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
