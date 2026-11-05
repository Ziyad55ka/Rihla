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

    @model_validator(mode="before")
    @classmethod
    def places_never_block(cls, data):
        # Places are wishes Rihla combines, so older Essential places saved
        # before this change no longer block generation or ask for review.
        if not isinstance(data, dict) or "destinations" not in (
            list(data.get("conflicts") or []) + list(data.get("own_review") or [])
        ):
            return data
        conflicts = [
            item for item in data.get("conflicts") or [] if item != "destinations"
        ]
        review = [
            item for item in data.get("own_review") or [] if item != "destinations"
        ]
        return {
            **data,
            "conflicts": conflicts,
            "own_review": review,
            "can_generate": not conflicts,
        }

    @model_validator(mode="after")
    def blocked_while_conflicted(self):
        if self.can_generate == bool(self.conflicts):
            raise ValueError("Generation is allowed only with no conflicts.")
        return self
