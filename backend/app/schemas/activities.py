from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.proposals import StrictModel


class SelectionRequest(StrictModel):
    version: int = Field(ge=1)
    activity_ids: list[UUID] = Field(max_length=300)

    @model_validator(mode="after")
    def unique_ids(self):
        if len(set(self.activity_ids)) != len(self.activity_ids):
            raise ValueError("Activity selections must be unique.")
        return self


class ActivitySelections(SelectionRequest):
    proposal_id: UUID
