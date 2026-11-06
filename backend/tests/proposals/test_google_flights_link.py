from datetime import date
from urllib.parse import parse_qs, urlparse

from app.schemas.proposals import FlightLeg, Flights, FlightSegment, InfoField, SarPrice
from app.services.flight_prices import FareLeg, leg_segments
from app.services.google_flights_link import itinerary_url
from app.services.proposal_generation import _fare_leg

# Google Flights' own link for RUH-IST, SV 1465 + SV 251 out, SV 264 back, 2 adults,
# taken from its booking page on 6 Nov 2026.
GOOGLE_TFS = (
    "CBwQAhphEgoyMDI2LTEyLTEwIiAKA1JVSBIKMjAyNi0xMi0xMBoDTUVEKgJTVjIEMTQ2NSIfCgNNRUQS"
    "CjIwMjYtMTItMTAaA0lTVCoCU1YyAzI1MWoHCAESA1JVSHIHCAESA0lTVBo_EgoyMDI2LTEyLTE2Ih8K"
    "A0lTVBIKMjAyNi0xMi0xNhoDUlVIKgJTVjIDMjY0agcIARIDSVNUcgcIARIDUlVIQAFAAUgBcAGYAQE"
)
NONE = InfoField(value=None, status="Not available", evidence=[])
NO_PRICE = SarPrice(amount_sar=None, status="Not available", evidence=[])


def seg(origin, day, destination, carrier, number):
    return FlightSegment(
        from_airport=origin,
        date=date.fromisoformat(day),
        to_airport=destination,
        carrier=carrier,
        number=number,
    )


def leg(direction, day, segments):
    return FlightLeg(
        direction=direction,
        date=date.fromisoformat(day),
        airline=NONE,
        duration=NONE,
        price=NO_PRICE,
        booking_url=None,
        segments=segments,
    )


def route(outbound, back, trip_type="round_trip", origin_airport="RUH"):
    legs = [leg("outbound", outbound[0].date.isoformat(), outbound)]
    if back is not None:
        legs.append(leg("return", back[0].date.isoformat(), back))
    return Flights(
        origin="Riyadh",
        trip_type=trip_type,
        legs=legs,
        airline=NONE,
        duration=NONE,
        price_per_person=NO_PRICE,
        origin_airport=origin_airport,
    )


ISTANBUL = (
    [
        seg("RUH", "2026-12-10", "MED", "SV", "1465"),
        seg("MED", "2026-12-10", "IST", "SV", "251"),
    ],
    [seg("IST", "2026-12-16", "RUH", "SV", "264")],
)


def tfs(url):
    return parse_qs(urlparse(url).query)["tfs"][0]


def test_matches_google_flights_own_link_byte_for_byte():
    url = itinerary_url(route(*ISTANBUL), 2)
    assert url.startswith("https://www.google.com/travel/flights?")
    assert tfs(url) == GOOGLE_TFS


def test_one_entry_per_traveller():
    one, three = itinerary_url(route(*ISTANBUL), 1), itinerary_url(route(*ISTANBUL), 3)
    assert tfs(one) != tfs(three) != GOOGLE_TFS


def test_never_clamps_a_group_to_fewer_passengers_or_opens_other_dates():
    from datetime import timedelta

    current = route(*ISTANBUL)
    assert itinerary_url(current, 10) is None
    assert itinerary_url(current, 0) is None
    current.legs[0].date += timedelta(days=1)
    assert itinerary_url(current, 2) is None


def test_booking_airports_must_match_the_route_metadata():
    current = route(*ISTANBUL)
    current.destination_airport = "CAI"
    assert itinerary_url(current, 2) is None
    current.destination_airport = "IST"
    current.return_airport = "CDG"
    assert itinerary_url(current, 2) is None


def test_connection_leaving_the_next_day_keeps_its_own_date():
    out = [
        seg("RUH", "2026-12-10", "JED", "XY", "55"),
        seg("JED", "2026-12-11", "GYD", "XY", "627"),
    ]
    url = itinerary_url(route(out, [seg("GYD", "2026-12-16", "RUH", "XY", "324")]), 2)
    assert url is not None


def test_no_link_when_a_detail_is_missing_or_does_not_fit():
    out, back = ISTANBUL
    assert itinerary_url(None, 2) is None
    assert itinerary_url(route(out, None, trip_type="one_way"), 2) is None
    assert itinerary_url(route(out, back, trip_type="split"), 2) is None
    # Older proposals have no segments.
    assert itinerary_url(_without_segments(), 2) is None
    # A gap in the connection would open another trip.
    broken = [out[0], seg("JED", "2026-12-10", "IST", "SV", "251")]
    assert itinerary_url(route(broken, back), 2) is None
    # The return must come home to the departure airport.
    assert (
        itinerary_url(route(out, [seg("IST", "2026-12-16", "JED", "SV", "264")]), 2)
        is None
    )
    assert itinerary_url(route(out, back, origin_airport="JED"), 2) is None


def _without_segments():
    flights = route(*ISTANBUL)
    legs = [item.model_copy(update={"segments": []}) for item in flights.legs]
    return flights.model_copy(update={"legs": legs})


def test_segments_come_from_the_source_and_reach_the_proposal():
    part = {
        "segments": [
            {
                "departure_airport": "RUH",
                "departure_time_local": "2026-12-10T23:45:00",
                "arrival_airport": "JED",
                "marketing_carrier_code": "XY",
                "flight_number": "55",
            },
            {
                "departure_airport": "JED",
                "departure_time_local": "2026-12-11T06:10:00",
                "arrival_airport": "GYD",
                "marketing_carrier_code": "XY",
                "flight_number": "627",
            },
        ]
    }
    found = leg_segments(part)
    assert found == (
        ("RUH", "2026-12-10", "JED", "XY", "55"),
        ("JED", "2026-12-11", "GYD", "XY", "627"),
    )
    fare_leg = FareLeg(
        "outbound", "2026-12-10", "flynas", 735, None, None, None, segments=found
    )
    shown = _fare_leg(fare_leg, [])
    assert [item.date for item in shown.segments] == [
        date(2026, 12, 10),
        date(2026, 12, 11),
    ]


def test_any_missing_segment_detail_gives_no_segments():
    part = {
        "segments": [
            {
                "departure_airport": "RUH",
                "arrival_airport": "JED",
                "flight_number": "55",
            }
        ]
    }
    assert leg_segments(part) == ()
    bad = FareLeg(
        "outbound",
        "2026-12-10",
        "x",
        1,
        None,
        None,
        None,
        segments=(("RUH", "bad", "JED", "XY", "55"),),
    )
    assert _fare_leg(bad, []).segments == []
