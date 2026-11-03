import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field

from app.core.auth import CurrentIdentity
from app.schemas.proposals import Proposal, StrictModel
from app.services.activity_research import find_activities
from app.services.generation_inputs import GenerationInputsError, _secret_rpc
from app.services.trip_research import ResearchError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/trips", tags=["activities"])


class SuggestionRequest(StrictModel):
    version: int = Field(ge=1)


@router.post("/{trip_id}/proposals/{proposal_id}/activities/suggestions")
async def suggestions(
    trip_id: UUID,
    proposal_id: UUID,
    body: SuggestionRequest,
    identity: CurrentIdentity,
    request: Request,
):
    settings = request.app.state.settings
    # This feature never falls back to saved demo proposals or synthetic activities.
    if not settings.gemini_api_key or not settings.tavily_api_key:
        raise HTTPException(503, "Activity search is not configured on the backend.")
    token = uuid4()
    args = {
        "p_trip_id": str(trip_id),
        "p_proposal_id": str(proposal_id),
        "p_user_id": str(identity.account.id),
        "p_version": body.version,
        "p_token": str(token),
    }
    started = False
    try:
        job = (
            await _secret_rpc("rihla_begin_activity_research", args, settings, None)
        ).json()
        if job["ready"]:
            return {"ready": True}
        if not job["started"]:
            raise HTTPException(409, "Activity search is busy. Try again shortly.")
        started = True
        proposal = Proposal.model_validate(job["proposal"])
        enriched = await find_activities(proposal, settings)
        await _secret_rpc(
            "rihla_finish_activity_research",
            {
                **args,
                "p_cities": [s.model_dump(mode="json") for s in enriched.cities],
                "p_sources": [s.model_dump(mode="json") for s in enriched.sources],
            },
            settings,
            None,
        )
        return {"ready": True}
    except ResearchError as error:
        # Codes only: the message and sources may describe the trip.
        logger.info("activity_search_failed stage=research code=%s", error.code)
        raise HTTPException(
            503, "Activity search is unavailable. Try again later."
        ) from error
    except GenerationInputsError as error:
        logger.info("activity_search_failed stage=database code=%s", error.code)
        code = (
            403
            if error.code == "access_denied"
            else 409
            if error.code == "proposal_not_found"
            else 503
        )
        raise HTTPException(
            code, "Activity search could not be completed. Reload and try again."
        ) from error
    finally:
        if started:
            try:
                await _secret_rpc(
                    "rihla_fail_activity_research",
                    {"p_token": str(token)},
                    settings,
                    None,
                )
            except GenerationInputsError:
                pass  # An expired lease will recover without exposing provider errors.
