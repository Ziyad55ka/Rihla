"""One seller booking must cover both directions; never merge two one-way links."""

from collections.abc import Iterable
from urllib.parse import urlsplit


def complete_ground_route(
    cities: Iterable[str], arrival_airport: str | None, return_airport: str | None
) -> bool:
    """A same-airport return needs an explicit final stay in the arrival city.

    Otherwise the last intercity journey and its cost disappear from the plan.
    An actual open-jaw ticket can leave from the last city instead.
    """
    names = tuple(" ".join(city.casefold().split()) for city in cities)
    if len(names) < 2 or not arrival_airport:
        return True
    return bool(
        (return_airport and return_airport != arrival_airport) or names[0] == names[-1]
    )


def single_booking(trip_type: str, booking_urls: Iterable[str | None]) -> bool:
    urls = tuple(booking_urls)
    if trip_type != "round_trip" or len(urls) != 2 or not urls[0] or urls[0] != urls[1]:
        return False
    url = urls[0]
    if len(url) > 2000 or any(ord(char) < 32 for char in url):
        return False
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return bool(
        parts.scheme == "https"
        and parts.hostname
        and not parts.username
        and not parts.password
    )
