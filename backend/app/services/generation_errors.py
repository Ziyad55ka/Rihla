"""Errors that end generation with a clear reason and things the group can change.

Every message speaks about the group in general: never a member, a budget or a
departure city, because any member of the trip may read it.
"""

from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel

from app.schemas.generation import GenerationInput

Action = Literal["edit_dates", "edit_preferences", "retry"]
# The page shows its own translated text for each kind; `text` is the English copy.
Kind = Literal[
    "dates_too_soon",
    "widen_dates",
    "add_destination",
    "retry_later",
    "generate_again",
    "review_essentials",
    "wait_and_retry",
]


class Suggestion(BaseModel):
    action: Action
    kind: Kind
    text: str
    # Values the text uses, such as {"earliest": "2026-11-06", "days": "3"}.
    params: dict[str, str] = {}


class GenerationNeedsChanges(Exception):
    """No proposal could be built. Carries why and what the group can try."""

    def __init__(
        self,
        code: Literal["no_flights", "no_proposals"],
        message: str,
        suggestions: list[Suggestion],
        places: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.suggestions = suggestions
        self.places = places or []

    def detail(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "places": self.places,
            "suggestions": [item.model_dump() for item in self.suggestions],
        }


def earliest_departure(today: date, lead_days: int) -> date:
    return today + timedelta(days=lead_days)


def no_flights_error(
    generation: GenerationInput,
    tried: list[str],
    today: date,
    lead_days: int,
    nights_hint: int | None,
) -> GenerationNeedsChanges:
    """Build the message after every planned destination had no bookable flights."""
    places = ", ".join(dict.fromkeys(tried)) if tried else ""
    message = (
        f"No bookable flights were found to {places} for the group's dates."
        if places
        else "No bookable flights were found for the group's dates."
    )
    suggestions: list[Suggestion] = []
    earliest = earliest_departure(today, lead_days)
    if generation.shared_start < earliest:
        suggestions.append(
            Suggestion(
                action="edit_dates",
                kind="dates_too_soon",
                params={"earliest": earliest.isoformat(), "days": str(lead_days)},
                text=(
                    f"Trips need to start at least {lead_days} days from today so "
                    f"seats can still be booked. Move the group's dates to start on "
                    f"{earliest.isoformat()} or later."
                ),
            )
        )
    spare = (generation.shared_end - generation.shared_start).days - (nights_hint or 0)
    if spare < 3:
        suggestions.append(
            Suggestion(
                action="edit_dates",
                kind="widen_dates",
                text=(
                    "Widen the group's shared dates by a few days, so other departure "
                    "days can be checked."
                ),
            )
        )
    suggestions.append(
        Suggestion(
            action="edit_preferences",
            kind="add_destination",
            text=(
                "Add another destination, or mark the destination Flexible, so Rihla "
                "can suggest places that have flights from every departure city."
            ),
        )
    )
    suggestions.append(
        Suggestion(
            action="retry",
            kind="retry_later",
            text="Try again later: airlines add and release seats during the day.",
        )
    )
    return GenerationNeedsChanges(
        "no_flights", message, suggestions, list(dict.fromkeys(tried))
    )


def no_proposals_error() -> GenerationNeedsChanges:
    return GenerationNeedsChanges(
        "no_proposals",
        "No proposal passed Rihla's checks this time.",
        [
            Suggestion(
                action="retry",
                kind="generate_again",
                text="Generate again: the AI suggests different places each time.",
            ),
            Suggestion(
                action="edit_preferences",
                kind="review_essentials",
                text=(
                    "Review Essential preferences: fewer Essential items give the AI "
                    "more places to choose from."
                ),
            ),
        ],
    )
