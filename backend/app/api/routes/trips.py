from uuid import UUID

from fastapi import APIRouter

from app.core.auth import CurrentIdentity
from app.schemas.planning import PlanningStatus
from app.schemas.preferences import MemberPreferences, SavedPreferences
from app.schemas.trips import (
    CreateTrip,
    InvitationCreated,
    InvitationStatus,
    JoinResult,
    JoinTrip,
    TripDetail,
    TripSummary,
)
from app.services.supabase import SupabaseHTTP
from app.services.trips import trip_rpc

router = APIRouter(prefix="/api/trips", tags=["trips"])


@router.get("/{trip_id}/planning", response_model=PlanningStatus)
async def read_planning_status(
    trip_id: UUID, identity: CurrentIdentity, client: SupabaseHTTP
):
    return await trip_rpc(
        client,
        identity,
        "rihla_get_planning_status",
        {"p_trip_id": str(trip_id)},
        PlanningStatus,
    )


@router.get("/{trip_id}/preferences", response_model=SavedPreferences)
async def read_preferences(
    trip_id: UUID, identity: CurrentIdentity, client: SupabaseHTTP
):
    return await trip_rpc(
        client,
        identity,
        "rihla_get_preferences",
        {"p_trip_id": str(trip_id)},
        SavedPreferences,
    )


@router.put("/{trip_id}/preferences", response_model=SavedPreferences)
async def save_preferences(
    trip_id: UUID,
    body: MemberPreferences,
    identity: CurrentIdentity,
    client: SupabaseHTTP,
):
    return await trip_rpc(
        client,
        identity,
        "rihla_save_preferences",
        {"p_trip_id": str(trip_id), "p_preferences": body.model_dump(mode="json")},
        SavedPreferences,
    )


@router.get("", response_model=list[TripSummary])
async def list_trips(identity: CurrentIdentity, client: SupabaseHTTP):
    return await trip_rpc(client, identity, "rihla_list_trips", {}, list[TripSummary])


@router.post("", response_model=TripDetail, status_code=201)
async def create_trip(
    body: CreateTrip, identity: CurrentIdentity, client: SupabaseHTTP
):
    return await trip_rpc(
        client,
        identity,
        "rihla_create_trip",
        {"p_title": body.title, "p_description": body.description},
        TripDetail,
    )


@router.post("/join", response_model=JoinResult)
async def join_trip(body: JoinTrip, identity: CurrentIdentity, client: SupabaseHTTP):
    return await trip_rpc(
        client,
        identity,
        "rihla_join_trip",
        {"p_token": body.token},
        JoinResult,
    )


@router.get("/{trip_id}", response_model=TripDetail)
async def read_trip(trip_id: UUID, identity: CurrentIdentity, client: SupabaseHTTP):
    return await trip_rpc(
        client,
        identity,
        "rihla_get_trip",
        {"p_trip_id": str(trip_id)},
        TripDetail,
    )


@router.get("/{trip_id}/invitation", response_model=InvitationStatus)
async def read_invitation(
    trip_id: UUID, identity: CurrentIdentity, client: SupabaseHTTP
):
    return await trip_rpc(
        client,
        identity,
        "rihla_get_invitation",
        {"p_trip_id": str(trip_id)},
        InvitationStatus,
    )


@router.post("/{trip_id}/invitation", response_model=InvitationCreated, status_code=201)
async def issue_invitation(
    trip_id: UUID, identity: CurrentIdentity, client: SupabaseHTTP
):
    return await trip_rpc(
        client,
        identity,
        "rihla_issue_invitation",
        {"p_trip_id": str(trip_id)},
        InvitationCreated,
    )


@router.delete("/{trip_id}/invitation", response_model=InvitationStatus)
async def revoke_invitation(
    trip_id: UUID, identity: CurrentIdentity, client: SupabaseHTTP
):
    return await trip_rpc(
        client,
        identity,
        "rihla_revoke_invitation",
        {"p_trip_id": str(trip_id)},
        InvitationStatus,
    )
