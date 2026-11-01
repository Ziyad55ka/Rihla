"""What blocks generation, by category only."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ConflictCategory = Literal[
    "readiness", "dates", "destinations", "flights", "accommodation", "budget"
]


class GroupConflicts(BaseModel):
    """Shown to every member. Categories only, like the group date conflict."""

    model_config = ConfigDict(extra="forbid")
    conflicts: list[ConflictCategory]
    # This member has an Essential in these categories and should review it.
    own_review: list[ConflictCategory]
    can_generate: bool = Field(strict=True)

    @model_validator(mode="after")
    def blocked_while_conflicted(self):
        if self.can_generate == bool(self.conflicts):
            raise ValueError("Generation is allowed only with no conflicts.")
        return self
