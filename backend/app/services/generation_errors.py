"""Errors that end generation with a clear reason and things the group can change.

Every message speaks about the group in general: never a member, a budget or a
departure city, because any member of the trip may read it.
"""

from datetime import date, timedelta
from typing import Literal
from urllib.parse import urlencode

from pydantic import BaseModel

from app.schemas.generation import GenerationInput

Action = Literal["edit_dates", "edit_preferences", "retry", "open_link"]
# The page shows its own translated text for each kind; `text` is the English copy.
Kind = Literal[
    "dates_too_soon",
    "widen_dates",
    "add_destination",
    "retry_later",
    "generate_again",
    "review_essentials",
    "wait_and_retry",
    "search_google_flights",
    "try_other_dates",
]

# Live fares are cached for minutes only, so after this long a new search sees
# seats the airlines have opened since. Long enough for real changes to appear.
RETRY_AFTER_HOURS = 2


class Suggestion(BaseModel):
    action: Action
    kind: Kind
    text: str
    # Values the text uses, such as {"earliest": "2026-11-06", "days": "3"}.
    params: dict[str, str] = {}


# Why the searches found nothing, most frequent first. The page translates each.
CAUSE_TEXT = {
    "dates_not_searchable": (
        "The flight source does not search these dates yet, usually because they "
        "are far ahead. Try earlier dates."
    ),
    "no_seats": (
        "No flight that day has enough seats left for everyone flying from the "
        "same city together."
    ),
    "lands_after_trip": (
        "There are flights, but the only ones home land after the group's last day."
    ),
    "no_single_booking": (
        "Flights exist, but outbound and return can only be bought as two separate "
        "bookings, which Rihla does not offer."
    ),
    "not_on_sale": (
        "The flights listed are no longer on sale on the airline's or Google's site."
    ),
}


class Cause(BaseModel):
    kind: str
    text: str


def causes_from(counts: dict[str, int]) -> list[Cause]:
    ordered = sorted(counts.items(), key=lambda item: -item[1])
    return [
        Cause(kind=kind, text=CAUSE_TEXT[kind])
        for kind, _ in ordered
        if kind in CAUSE_TEXT
    ]


class GenerationNeedsChanges(Exception):
    """No proposal could be built. Carries why and what the group can try."""

    def __init__(
        self,
        code: Literal["no_flights", "no_proposals", "dates_unavailable"],
        message: str,
        suggestions: list[Suggestion],
        places: list[str] | None = None,
        causes: list[Cause] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.suggestions = suggestions
        self.places = places or []
        self.causes = causes or []

    def detail(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "places": self.places,
            "causes": [item.model_dump() for item in self.causes],
            "suggestions": [item.model_dump() for item in self.suggestions],
        }


def earliest_departure(today: date, lead_days: int) -> date:
    return today + timedelta(days=lead_days)


def google_flights_search(place: str, start: date, end: date) -> str:
    """A Google Flights search for the group's dates. It names no departure city:
    any member may read it, and Google fills in the reader's own location."""
    query = f"Flights to {place} on {start.isoformat()} through {end.isoformat()}"
    return "https://www.google.com/travel/flights?" + urlencode({"q": query})


def no_flights_error(
    generation: GenerationInput,
    tried: list[str],
    today: date,
    lead_days: int,
    nights_hint: int | None,
    reasons: dict[str, int] | None = None,
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
    too_soon = generation.shared_end < earliest
    if too_soon:
        message = (
            "The shared dates end before the earliest bookable departure. "
            "Change the group dates before generating."
        )
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
    elif not too_soon:
        suggestions.append(
            Suggestion(
                action="edit_dates",
                kind="try_other_dates",
                text=(
                    "Try other travel dates: flights on other days may have seats "
                    "for everyone, or better fares."
                ),
            )
        )
    suggestions.append(
        Suggestion(
            action="edit_preferences",
            kind="add_destination",
            text=(
                "Add more places to your preferences, or leave them empty, so Rihla "
                "can look at more places with flights from every departure city."
            ),
        )
    )
    if tried and not too_soon:
        place = tried[0]
        suggestions.append(
            Suggestion(
                action="open_link",
                kind="search_google_flights",
                text=(
                    f"Search Google Flights for {place} yourself. Rihla does not "
                    "make a trip until it finds tickets the whole group can book."
                ),
                params={
                    "place": place,
                    "url": google_flights_search(
                        place, generation.shared_start, generation.shared_end
                    ),
                },
            )
        )
    suggestions.append(
        Suggestion(
            action="retry",
            kind="retry_later",
            text=(
                f"Try again in about {RETRY_AFTER_HOURS} hours: airlines add and "
                "release seats during the day, and Rihla checks live each time."
            ),
            params={"hours": str(RETRY_AFTER_HOURS)},
        )
    )
    return GenerationNeedsChanges(
        "dates_unavailable" if too_soon else "no_flights",
        message,
        suggestions,
        list(dict.fromkeys(tried)),
        causes_from(reasons or {}),
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
