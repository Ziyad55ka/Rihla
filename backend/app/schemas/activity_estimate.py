from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.proposals import StrictModel


class EstimateComponent(StrictModel):
    known_amount_sar: Decimal = Field(default=Decimal("0.00"), ge=0)
    missing_items: int = Field(default=0, ge=0)
    unconfirmed_items: int = Field(default=0, ge=0)
    estimated_items: int = Field(default=0, ge=0)


class ActivityProposalEstimate(StrictModel):
    proposal_id: UUID
    version: int = Field(ge=1)
    currency: Literal["SAR"] = "SAR"
    flights: EstimateComponent
    accommodation: EstimateComponent
    transport: EstimateComponent
    meals: EstimateComponent = Field(default_factory=EstimateComponent)
    activities: EstimateComponent
    total: EstimateComponent
