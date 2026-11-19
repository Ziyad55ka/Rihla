"""Server-only Supabase RPCs for proposals and their notification queue."""

from decimal import Decimal
from uuid import UUID

import httpx2 as httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import Settings
from app.schemas.generation import GenerationInput
from app.schemas.proposals import BudgetStatus, Flights, Proposal
from app.services.proposal_costs import CostContext


class GenerationInputsError(Exception):
    """A safe, general failure. It holds no response body and no key."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def private_rpc_configured(settings: Settings) -> bool:
    return bool(settings.supabase_url and settings.supabase_secret_key)


async def _secret_rpc(
    name: str,
    args: dict,
    settings: Settings,
    transport: httpx.AsyncBaseTransport | None,
) -> httpx.Response:
    if not private_rpc_configured(settings):
        raise GenerationInputsError("not_configured")
    key = settings.supabase_secret_key
    headers = {"apikey": key}
    # A legacy service_role key is a JWT and also goes here; sb_secret_ keys do not.
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    try:
        async with httpx.AsyncClient(
            base_url=settings.supabase_url.rstrip("/") + "/",
            headers=headers,
            timeout=5.0,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        ) as client:
            response = await client.post(f"rest/v1/rpc/{name}", json=args)
    except httpx.RequestError as error:
        raise GenerationInputsError("unavailable") from error
    if response.status_code != 200:
        body = response.text
        if "revision_stale" in body:
            raise GenerationInputsError("revision_stale")
        if "generation_not_ready" in body:
            raise GenerationInputsError("not_ready")
        if "proposal_not_found" in body:
            raise GenerationInputsError("proposal_not_found")
        if "trip_access_denied" in body:
            raise GenerationInputsError("access_denied")
        raise GenerationInputsError("unavailable")
    return response


class TripEmail(BaseModel):
    id: UUID
    lease: UUID
    email: str
    trip_id: UUID
    proposal_id: UUID | None


async def claim_trip_email(settings: Settings) -> TripEmail | None:
    response = await _secret_rpc("rihla_claim_trip_email", {}, settings, None)
    job = response.json()
    return TripEmail.model_validate(job) if job else None


async def finish_trip_email(job: TripEmail, outcome: str, settings: Settings) -> None:
    await _secret_rpc(
        "rihla_finish_trip_email",
        {"p_id": str(job.id), "p_lease": str(job.lease), "p_outcome": outcome},
        settings,
        None,
    )


class RevisionContext(BaseModel):
    token: str
    proposal: Proposal


async def revision_context(args: dict, settings: Settings) -> RevisionContext:
    response = await _secret_rpc("rihla_revision_context", args, settings, None)
    return RevisionContext.model_validate_json(response.content)


async def save_revision(args: dict, settings: Settings) -> None:
    await _secret_rpc("rihla_save_revision", args, settings, None)


class FlightContext(BaseModel):
    """Private to the backend: a count, a budget and every city's flights."""

    city: str | None
    # Everyone flying from the caller's departure city.
    adults: int
    # The group's lowest budget.
    ceiling: Decimal = Field(gt=0, allow_inf_nan=False)
    proposal: Proposal


async def fetch_flight_context(
    trip_id: UUID,
    proposal_id: UUID,
    member_id: UUID,
    settings: Settings,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FlightContext:
    response = await _secret_rpc(
        "rihla_flight_context",
        {
            "p_trip_id": str(trip_id),
            "p_proposal_id": str(proposal_id),
            "p_user_id": str(member_id),
        },
        settings,
        transport,
    )
    try:
        return FlightContext.model_validate_json(response.content)
    except ValidationError as error:
        raise GenerationInputsError("invalid_response") from error


async def fetch_cost_context(
    trip_id: UUID,
    member_id: UUID,
    settings: Settings,
    transport: httpx.AsyncBaseTransport | None = None,
) -> CostContext:
    """US-13: the member's own budget and the group's flights, for totals only."""
    response = await _secret_rpc(
        "rihla_cost_context",
        {"p_trip_id": str(trip_id), "p_user_id": str(member_id)},
        settings,
        transport,
    )
    try:
        return CostContext.model_validate_json(response.content)
    except ValidationError as error:
        raise GenerationInputsError("invalid_response") from error


async def save_flight_refresh(
    trip_id: UUID,
    proposal_id: UUID,
    member_id: UUID,
    flights: Flights,
    budget_status: BudgetStatus | None,
    settings: Settings,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    await _secret_rpc(
        "rihla_save_flight_refresh",
        {
            "p_trip_id": str(trip_id),
            "p_proposal_id": str(proposal_id),
            "p_user_id": str(member_id),
            "p_flights": flights.model_dump(mode="json"),
            "p_budget_status": budget_status,
        },
        settings,
        transport,
    )


async def fetch_generation_inputs(
    trip_id: UUID,
    admin_id: UUID,
    settings: Settings,
    transport: httpx.AsyncBaseTransport | None = None,
) -> GenerationInput:
    response = await _secret_rpc(
        "rihla_trip_generation_inputs",
        {"p_trip_id": str(trip_id), "p_admin_id": str(admin_id)},
        settings,
        transport,
    )
    try:
        return GenerationInput.model_validate_json(response.content)
    except ValidationError as error:
        raise GenerationInputsError("invalid_response") from error


async def save_generated_proposals(
    trip_id: str,
    admin_id: UUID,
    version: int,
    input_hash: str,
    complete: bool,
    proposals: list[Proposal],
    settings: Settings,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    await _secret_rpc(
        "rihla_save_proposals",
        {
            "p_trip_id": trip_id,
            "p_admin_id": str(admin_id),
            "p_version": version,
            "p_input_hash": input_hash,
            "p_complete": complete,
            "p_proposals": [item.model_dump(mode="json") for item in proposals],
        },
        settings,
        transport,
    )
