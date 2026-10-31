"""Turn a stored proposal into what one member may receive."""

from typing import Literal

from app.schemas.proposals import Proposal


def _same_city(first: str, second: str) -> bool:
    return first.strip().casefold() == second.strip().casefold()


def view_for_member(
    proposal: Proposal,
    departure_city: str,
    visibility: Literal["own", "all"] = "own",
) -> Proposal:
    """Every browser response must use this, or other members' cities can leak."""
    flights = proposal.flights
    if visibility == "own":
        flights = [
            route for route in flights if _same_city(route.origin, departure_city)
        ]
    view = proposal.model_copy(update={"flights": flights})

    # A source link can name another member's city, so keep only those still cited.
    cited = {
        item.source_id for field in view.evidence_fields() for item in field.evidence
    }
    return view.model_copy(
        update={
            "sources": [source for source in view.sources if source.id in cited],
        }
    )
