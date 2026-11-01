from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from app.core.auth import CurrentIdentity
from app.schemas.planning import GroupConflicts
from app.schemas.proposals import Proposal
from app.services.generation_inputs import (
    GenerationInputsError,
    fetch_generation_inputs,
)
from app.services.generation_precheck import generate_checked
from app.services.proposal_generation import GenerationBlocked
from app.services.proposal_store import SupabaseProposalStore
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


class GeneratedProposals(StoredProposals):
    message: str | None
    reused: bool
    demo: bool


async def _read(trip_id: UUID, identity, client) -> StoredProposals:
    # Filtered by departure city inside the database, for every caller.
    return await trip_rpc(
        client,
        identity,
        "rihla_get_proposals",
        {"p_trip_id": str(trip_id)},
        StoredProposals,
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
    trip_id: UUID, identity: CurrentIdentity, client: SupabaseHTTP
):
    return await _read(trip_id, identity, client)


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

    stored = await _read(trip_id, identity, client)
    return GeneratedProposals(
        **stored.model_dump(),
        message=result.message,
        reused=result.reused,
        demo=result.demo,
    )
