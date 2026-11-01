from uuid import UUID

from fastapi import APIRouter

from app.core.auth import CurrentIdentity
from app.schemas.activities import ActivitySelections, SelectionRequest
from app.services.supabase import SupabaseHTTP
from app.services.trips import trip_rpc

router = APIRouter(prefix="/api/trips", tags=["activities"])


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
    return await trip_rpc(
        client,
        identity,
        "rihla_get_activity_selection",
        {
            "p_trip_id": str(trip_id),
            "p_proposal_id": str(proposal_id),
        },
        ActivitySelections,
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
):
    return await trip_rpc(
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
