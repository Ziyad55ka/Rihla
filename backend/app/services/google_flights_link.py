"""A Google Flights page with this exact round trip already chosen, both ways.

The airlines' own links do not always hold a chosen flight: Saudia's opened a
"flight no longer available" notice on 6 Nov 2026, and flynas's returned an error
page. This page lists the same two flights, for the whole group, with every seller
and its round-trip total, and "Continue" opens that seller with a fresh session.

The link carries the same `tfs` field Google Flights builds itself: a protobuf with
one entry per direction and one per segment (from, date, to, airline, number).
Checked byte for byte against Google's own link on 6 Nov 2026. Every segment needs
its own departure date: without it Google shows "Oops, something went wrong".
"""

import base64
from urllib.parse import urlencode

from app.schemas.proposals import Flights, FlightSegment

GOOGLE_FLIGHTS_URL = "https://www.google.com/travel/flights"


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _field(number: int, value: int | str | bytes) -> bytes:
    if isinstance(value, int):
        return _varint(number << 3) + _varint(value)
    data = value.encode() if isinstance(value, str) else value
    return _varint(number << 3 | 2) + _varint(len(data)) + data


def _airport(code: str) -> bytes:
    return _field(1, 1) + _field(2, code)


def _segment(segment: FlightSegment) -> bytes:
    return _field(
        4,
        _field(1, segment.from_airport)
        + _field(2, segment.date.isoformat())
        + _field(3, segment.to_airport)
        + _field(5, segment.carrier)
        + _field(6, segment.number),
    )


def _direction(segments: list[FlightSegment]) -> bytes:
    first, last = segments[0], segments[-1]
    return _field(
        3,
        _field(2, first.date.isoformat())
        + b"".join(_segment(item) for item in segments)
        + _field(13, _airport(first.from_airport))
        + _field(14, _airport(last.to_airport)),
    )


def _connected(segments: list[FlightSegment]) -> bool:
    return all(
        earlier.to_airport == later.from_airport and earlier.date <= later.date
        for earlier, later in zip(segments, segments[1:], strict=False)
    )


def itinerary_url(route: Flights | None, adults: int) -> str | None:
    """The chosen round trip on Google Flights, or None when a detail is missing.

    Only a round trip whose every segment is known: a guess would open a different
    flight, which is worse than the search the page shows otherwise.
    """
    if route is None or route.trip_type != "round_trip" or len(route.legs) != 2:
        return None
    outbound, back = route.legs
    if outbound.direction != "outbound" or back.direction != "return":
        return None
    directions = [outbound.segments, back.segments]
    if not all(segments and _connected(segments) for segments in directions):
        return None
    if not 1 <= adults <= 9:
        return None  # Never silently open a booking for fewer travellers.
    if any(leg.segments[0].date != leg.date for leg in route.legs):
        return None
    if back.segments[-1].date > back.date:
        return None
    # A round trip ends where it began, unless it flies home from another city.
    home = outbound.segments[0].from_airport
    if back.segments[-1].to_airport != home:
        return None
    if route.origin_airport and route.origin_airport != home:
        return None
    destination = outbound.segments[-1].to_airport
    if route.destination_airport and route.destination_airport != destination:
        return None
    if back.segments[0].from_airport != (route.return_airport or destination):
        return None
    raw = (
        _field(1, 28)
        + _field(2, 2)
        + b"".join(_direction(segments) for segments in directions)
        + b"".join(_field(8, 1) for _ in range(adults))
        + _field(9, 1)
        + _field(14, 1)
        + _field(19, 1)
    )
    tfs = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    query = {"hl": "en", "gl": "sa", "curr": "SAR", "tfs": tfs, "tfu": "EgIIAQ"}
    return f"{GOOGLE_FLIGHTS_URL}?{urlencode(query)}"
