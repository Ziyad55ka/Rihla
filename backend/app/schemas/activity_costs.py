from uuid import UUID

from pydantic import BaseModel

from app.schemas.costs import CostAmount


class ActivityCostSelection(BaseModel):
    id: UUID
    activity_ids: list[UUID]
    group_cost: CostAmount


class ActivityCostSelections(BaseModel):
    proposals: list[ActivityCostSelection]
