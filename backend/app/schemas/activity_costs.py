from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.costs import CostAmount


class ActivityCostSelection(BaseModel):
    id: UUID
    activity_ids: list[UUID]
    group_cost: CostAmount
    # Backend-only context; legacy RPC responses do not contain these fields.
    has_selection: bool | None = None
    saved_members: int | None = Field(default=None, ge=0)


class ActivityCostSelections(BaseModel):
    proposals: list[ActivityCostSelection]
