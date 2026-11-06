"""Keep every planned hotel night unless an earlier checkout is explicitly chosen.

A flight before dawn does not establish the hotel's checkout policy or whether
travellers need the room that evening. Silently removing that night understates
the budget and can move a booking link to the wrong checkout date.
"""

from datetime import date

from app.schemas.proposals import CityStay, Flights

# Leaving the hotel for a flight before this hour means leaving the night before.
EARLY_HOME_HOUR = 6


def leaves_before_dawn(route: Flights, last_day: date) -> bool:
    back = next((leg for leg in route.legs if leg.direction == "return"), None)
    if back is None or not back.departure_time:
        return False
    when = back.departure_time
    if when[:10] != last_day.isoformat():
        return False
    try:
        return int(when[11:13]) < EARLY_HOME_HOUR
    except ValueError:
        return False


def last_night_unused(routes: list[Flights], last_day: date) -> bool:
    """Legacy hook: flight times alone never establish an unused paid night."""
    return False


def hotel_nights(
    stays: list[CityStay], routes: list[Flights], last_day: date
) -> list[int]:
    return [stay.nights for stay in stays]
