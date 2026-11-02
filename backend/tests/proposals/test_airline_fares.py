"""Each direction's price, and the airline fare table."""

from datetime import date
from decimal import Decimal

from test_flight_refresh import route

from app.services.airline_fares import fare_notes
from app.services.flight_prices import FlightQuery, fare_from_itinerary

QUERY = FlightQuery("RUH", "BAH", date(2026, 11, 20), date(2026, 11, 30), 1)


def side(number: str) -> dict:
    return {
        "carrier": "Gulf Air",
        "duration_minutes": 80,
        "segments": [{"marketing_carrier_code": "GF", "flight_number": number}],
    }


CHOICE = {
    "price": {"amount": 1614, "currency": "SAR", "status": "verified"},
    "outbound": side("162"),
    "inbound": side("163"),
}


def link(amount: float, url: str = "https://www.gulfair.com/x") -> dict:
    return {"url": url, "price": {"amount": amount, "currency": "SAR"}}


def option(legs: list[str], amount: float) -> dict:
    return {"legs": legs, "links": [link(amount)]}


WHOLE = option(["outbound", "inbound"], 1614)


def test_total_only_is_never_divided() -> None:
    fare = fare_from_itinerary(CHOICE, {"booking_options": [WHOLE]}, QUERY)

    assert fare.trip_type == "round_trip"
    assert [item.amount for item in fare.legs] == [None, None]
    assert Decimal(fare.amount) == Decimal(1614)


def test_each_direction_is_used_when_the_seller_states_it() -> None:
    fare = fare_from_itinerary(
        CHOICE,
        {
            "booking_options": [
                WHOLE,
                option(["outbound"], 999),
                option(["inbound"], 615),
            ]
        },
        QUERY,
    )

    assert [Decimal(item.amount) for item in fare.legs] == [Decimal(999), Decimal(615)]
    assert fare.trip_type == "round_trip"


def test_directions_that_do_not_add_up_are_not_shown() -> None:
    fare = fare_from_itinerary(
        CHOICE,
        {
            "booking_options": [
                WHOLE,
                option(["outbound"], 500),
                option(["inbound"], 500),
            ]
        },
        QUERY,
    )

    assert [item.amount for item in fare.legs] == [None, None]


def numbered(*numbers: str):
    found = route()
    return found.model_copy(
        update={
            "legs": [
                item.model_copy(update={"flight_number": number})
                for item, number in zip(found.legs, numbers, strict=True)
            ]
        }
    )


def test_fare_table_finds_airlines_from_flight_numbers() -> None:
    notes = fare_notes(numbered("GF 162", "GF 163"))

    assert [item.code for item in notes] == ["GF"]
    assert notes[0].fare_ar == "السياحية الخفيفة"
    assert notes[0].checked_kg == 25


def test_two_airlines_give_two_notes_and_unknown_gives_none() -> None:
    assert [item.code for item in fare_notes(numbered("A3 953", "VF 10"))] == []
    assert [item.code for item in fare_notes(numbered("FZ 848", "XY 234"))] == [
        "FZ",
        "XY",
    ]
    assert fare_notes(route()) == []


def test_only_confirmed_bags_have_a_value() -> None:
    notes = {item.code: item for item in fare_notes(numbered("FZ 1", "SV 1"))}

    assert notes["FZ"].checked_kg == 0
    assert notes["SV"].checked_kg is None


def test_stop_airports_come_from_the_segments() -> None:
    connecting = {
        "carrier": "Gulf Air",
        "duration_minutes": 300,
        "segments": [
            {
                "marketing_carrier_code": "GF",
                "flight_number": "1",
                "arrival_airport": "BAH",
            },
            {
                "marketing_carrier_code": "GF",
                "flight_number": "2",
                "arrival_airport": "CDG",
            },
        ],
    }
    fare = fare_from_itinerary(
        {**CHOICE, "outbound": connecting}, {"booking_options": [WHOLE]}, QUERY
    )

    assert fare.legs[0].stop_airports == ("BAH",)
    assert fare.legs[0].stops == 1
    assert fare.legs[1].stop_airports == ()
