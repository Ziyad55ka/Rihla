"""Stored proposals. Saving goes through the one module holding the secret key."""

import httpx2 as httpx

from app.core.auth import Identity
from app.core.config import Settings
from app.services.generation_inputs import save_generated_proposals
from app.services.proposal_generation import GenerationResult
from app.services.trip_research import ResearchCost
from app.services.trips import trip_rpc


class SupabaseProposalStore:
    def __init__(
        self,
        client: httpx.AsyncClient,
        identity: Identity,
        settings: Settings,
        version: int,
    ) -> None:
        self.client = client
        self.identity = identity
        self.settings = settings
        self.version = version

    async def load(self, trip_id: str, input_hash: str) -> GenerationResult | None:
        found = await trip_rpc(
            self.client,
            self.identity,
            "rihla_has_saved_proposals",
            {
                "p_trip_id": trip_id,
                "p_input_hash": input_hash,
                "p_max_age_hours": self.settings.saved_proposals_ttl_hours,
            },
            bool,
        )
        if not found:
            return None
        # The route reads the stored proposals through the member-filtered function.
        return GenerationResult(
            proposals=[],
            complete=True,
            message=None,
            failures=[],
            cost=ResearchCost(),
        )

    async def save(
        self, trip_id: str, input_hash: str, result: GenerationResult
    ) -> None:
        await save_generated_proposals(
            trip_id,
            self.identity.account.id,
            self.version,
            input_hash,
            result.complete,
            result.proposals,
            self.settings,
        )
