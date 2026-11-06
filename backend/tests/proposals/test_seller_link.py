import asyncio
from datetime import date
from decimal import Decimal

import httpx2 as httpx

from app.services.flight_prices import FlightQuery
from app.services.google_flights_check import (
    GoogleFlightsCheck,
    forwarded_url,
    seller_link,
)

QUERY = FlightQuery("RUH", "MAD", date(2026, 12, 17), date(2026, 12, 24), 3)
ETIHAD = (
    "https://digital.etihad.com/book/search?B_LOCATION_1=RUH&amp;TRAVELERS=ADT,ADT,ADT"
)


def flight(number, origin, destination, day):
    return {
        "flight_number": number,
        "departure_airport": {"id": origin, "time": f"{day} 10:30"},
        "arrival_airport": {"id": destination, "time": f"{day} 19:05"},
    }


OUT = {
    "flights": [
        flight("EY 554", "RUH", "AUH", "2026-12-17"),
        flight("EY 103", "AUH", "MAD", "2026-12-17"),
    ],
    "departure_token": "dep",
}
BACK = {
    "flights": [
        flight("EY 102", "MAD", "AUH", "2026-12-24"),
        flight("EY 559", "AUH", "RUH", "2026-12-24"),
    ],
    "booking_token": "book",
}

# Connection clocks must be chronological at the connecting airport.
OUT["flights"][0]["arrival_airport"]["time"] = "2026-12-17 12:30"
OUT["flights"][1]["departure_airport"]["time"] = "2026-12-17 14:30"
BACK["flights"][0]["arrival_airport"]["time"] = "2026-12-24 12:30"
BACK["flights"][1]["departure_airport"]["time"] = "2026-12-24 14:30"


def page(*sellers):
    return {
        "booking_options": [
            {
                "together": {
                    "book_with": name,
                    "airline": airline,
                    "price": price,
                    "booking_request": {
                        "url": "https://www.google.com/travel/clk/f",
                        "post_data": f"u={name}",
                    },
                }
            }
            for name, airline, price in sellers
        ]
    }


def checker(booking_page, forward):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "serpapi.com":
            params = request.url.params
            if "booking_token" in params:
                return httpx.Response(200, json=booking_page)
            if "departure_token" in params:
                return httpx.Response(200, json={"best_flights": [BACK]})
            return httpx.Response(200, json={"best_flights": [OUT]})
        return forward(request)

    return GoogleFlightsCheck("key", httpx.MockTransport(handler))


def forwards_to(url):
    return lambda request: httpx.Response(
        200, text=f"<html><head><meta content=\"0;url='{url}'\"></head></html>"
    )


def test_opens_the_airline_page_with_the_chosen_flights():
    check = checker(
        page(("Expedia", None, 5128), ("Etihad", True, 5286)), forwards_to(ETIHAD)
    )
    found = asyncio.run(
        seller_link(check, QUERY, ("EY554", "EY103"), ("EY102", "EY559"))
    )
    assert found is not None and found.seller == "Etihad" and found.airline
    assert found.total == Decimal("5286")
    assert (
        found.url.startswith("https://digital.etihad.com/") and "&amp;" not in found.url
    )
    assert check.requests_made == 3


def test_a_redirect_works_too_and_google_pages_are_refused():
    def redirect(request):
        return httpx.Response(302, headers={"location": "https://www.flyadeal.com/x"})  # noqa: E731

    check = checker(page(("flyadeal", True, 1516)), redirect)
    found = asyncio.run(
        seller_link(check, QUERY, ("EY554", "EY103"), ("EY102", "EY559"))
    )
    assert found.url == "https://www.flyadeal.com/x"
    assert forwarded_url("url='https://www.google.com/travel/flights'") is None
    assert forwarded_url("url='http://air.example/x'") is None


def test_nothing_when_the_flights_or_sellers_are_missing():
    check = checker(page(), forwards_to(ETIHAD))
    assert (
        asyncio.run(seller_link(check, QUERY, ("EY554", "EY103"), ("EY102", "EY559")))
        is None
    )
    check = checker(page(("Etihad", True, 5286)), forwards_to(ETIHAD))
    assert asyncio.run(seller_link(check, QUERY, ("SV1",), ("SV2",))) is None


def test_the_airline_is_used_even_when_google_hides_its_price():
    check = checker(
        page(("Expedia", None, 6868), ("Flynas", True, None)),
        forwards_to("https://booking.flynas.com/x"),
    )
    found = asyncio.run(
        seller_link(check, QUERY, ("EY554", "EY103"), ("EY102", "EY559"))
    )
    assert found.seller == "Flynas" and found.total is None
