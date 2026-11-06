from datetime import date
from decimal import Decimal

from app.schemas.proposals import CityStay, FlightLeg, Flights, InfoField, SarPrice
from app.services.hotel_nights import hotel_nights, last_night_unused

NONE = InfoField(value=None, status="Not available", evidence=[])
NO_PRICE = SarPrice(amount_sar=None, status="Not available", evidence=[])
LAST = date(2027, 1, 19)


def route(home_departure: str | None) -> Flights:
    def leg(direction, day, when):
        return FlightLeg(
            direction=direction,
            date=day,
            airline=NONE,
            duration=NONE,
            price=NO_PRICE,
            booking_url=None,
            departure_time=when,
        )

    return Flights(
        origin="Riyadh",
        trip_type="round_trip",
        legs=[
            leg("outbound", date(2027, 1, 14), "2027-01-14T08:50:00"),
            leg("return", LAST, home_departure),
        ],
        airline=NONE,
        duration=NONE,
        price_per_person=NO_PRICE,
    )


def stay(nights: int) -> CityStay:
    return CityStay(
        order=1,
        city="Dubai",
        nights=nights,
        hotel_name=NONE,
        hotel_price_per_night=SarPrice(
            amount_sar=Decimal("300"), status="Unconfirmed", evidence=[]
        ),
        booking_url=None,
    )


def test_flight_before_dawn_never_silently_removes_a_paid_hotel_night():
    assert hotel_nights([stay(5)], [route("2027-01-19T00:01:00")], LAST) == [5]
    assert not last_night_unused([route("2027-01-19T05:59:00")], LAST)


def test_a_daytime_flight_home_keeps_every_night():
    assert hotel_nights([stay(5)], [route("2027-01-19T12:00:00")], LAST) == [5]
    assert not last_night_unused([route("2027-01-19T06:00:00")], LAST)


def test_one_later_flight_keeps_the_night_for_the_whole_group():
    routes = [route("2027-01-19T00:01:00"), route("2027-01-19T19:50:00")]
    assert hotel_nights([stay(5)], routes, LAST) == [5]


def test_unknown_times_and_one_night_stops_are_left_alone():
    assert hotel_nights([stay(5)], [route(None)], LAST) == [5]
    assert hotel_nights([stay(1)], [route("2027-01-19T00:01:00")], LAST) == [1]
    assert hotel_nights([stay(3), stay(2)], [route("2027-01-19T02:00:00")], LAST) == [
        3,
        2,
    ]
    assert not last_night_unused([], LAST)
