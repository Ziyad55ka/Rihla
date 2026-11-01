"""Trip.com's adapter, the switch that keeps it off, links and photos. All fakes."""

import asyncio
from datetime import date
from decimal import Decimal

import httpx2 as httpx

from app.core.config import Settings
from app.schemas.proposals import PlaceImage
from app.services.flight_prices import (
    FlightQuery,
    IgnavError,
    fare_from_itinerary,
    link_is_exact,
    pick_link,
)
from app.services.place_images import ImageCache, fetch_place_image, with_place_images
from app.services.travel_providers import (
    find_hotel,
    live_flight_providers,
    live_hotel_providers,
)
from app.services.tripcom_provider import HotelQuery, TripComFlights, TripComHotels

QUERY = FlightQuery("RUH", "BAH", date(2026, 11, 20), date(2026, 11, 30), 2)
STAY = HotelQuery("Manama", date(2026, 11, 20), date(2026, 11, 30))


def answer(status: int, body=None, text: str = "") -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if body is not None:
            return httpx.Response(status, json=body)
        return httpx.Response(status, text=text)

    return httpx.MockTransport(handler)


def test_tripcom_stays_off_until_switched_on() -> None:
    off = Settings(_env_file=None, ignav_api_key="k")
    assert [item.name for item in live_flight_providers(off)] == ["ignav"]
    assert live_hotel_providers(off) == []

    on = Settings(_env_file=None, ignav_api_key="k", tripcom_enabled=True)
    assert [item.name for item in live_flight_providers(on)] == ["tripcom", "ignav"]
    assert [item.name for item in live_hotel_providers(on)] == ["tripcom"]


def test_source_order_comes_from_settings() -> None:
    settings = Settings(
        _env_file=None,
        ignav_api_key="k",
        tripcom_enabled=True,
        flight_providers=["ignav", "tripcom"],
    )
    assert [item.name for item in live_flight_providers(settings)] == [
        "ignav",
        "tripcom",
    ]
    settings = Settings(_env_file=None, ignav_api_key="k", flight_providers=[])
    assert live_flight_providers(settings) == []


FLIGHT = {
    "flightTicketLink": "https://www.trip.com/flights/x",
    "pricePerTicket": "500",
    "currency": "SAR",
    "airline": "Gulf Air",
    "flightNumber": "GF162",
    "flightDuration": "1h 20m",
    "departureTime": "2026-11-20 06:50",
    "arrivalTime": "2026-11-20 08:10",
    "returnAirline": "Gulf Air",
    "returnFlightNumber": "GF163",
    "returnFlightDuration": "1h 20m",
}


def test_tripcom_flights_become_the_common_shape_for_the_whole_party() -> None:
    source = TripComFlights(
        answer(200, {"bookFlightLink": "x", "recommendedListOfOtherFlights": [FLIGHT]})
    )

    body = asyncio.run(source.search(QUERY))

    option = body["itineraries"][0]
    # One ticket is priced, so two people cost twice as much, like any other source.
    assert Decimal(option["price"]["amount"]) == Decimal(1000)
    assert option["price"]["status"] == "unverified"
    assert option["outbound"]["segments"][0]["flight_number"] == "162"
    assert option["outbound"]["duration_minutes"] == 80

    links = asyncio.run(source.booking_links(option["ignav_id"]))
    fare = fare_from_itinerary(option, links, QUERY, True)
    assert fare.provider_name == "Trip.com"
    assert fare.legs[0].booking_url == "https://www.trip.com/flights/x"
    assert Decimal(fare.amount) == Decimal(500)
    assert source.requests_made == 1


def test_tripcom_failure_raises_the_common_error() -> None:
    source = TripComFlights(answer(404, text="<html>404</html>"))
    try:
        asyncio.run(source.search(QUERY))
    except IgnavError as error:
        assert str(error) == "http_404"
        assert "html" not in str(error)
    else:
        raise AssertionError("A failed source must raise.")


HOTEL = {
    "hotelName": "Mock Palace",
    "hotelCurrency": "SAR",
    "hotelPrice": 320,
    "hotelLink": "https://www.trip.com/hotels/x",
}


def test_tripcom_hotel_gives_name_price_link_and_source() -> None:
    source = TripComHotels(answer(200, {"hotelList": [HOTEL]}))

    offer = asyncio.run(find_hotel([source], STAY))

    assert (offer.name, offer.source) == ("Mock Palace", "Trip.com")
    assert offer.price_sar == Decimal("320.00")
    assert offer.url == "https://www.trip.com/hotels/x"


def test_tripcom_hotel_in_another_currency_or_with_a_bad_link_is_handled() -> None:
    other = TripComHotels(
        answer(200, {"hotelList": [{**HOTEL, "hotelCurrency": "USD"}]})
    )
    assert asyncio.run(other.find(STAY)) is None
    bad = TripComHotels(
        answer(200, {"hotelList": [{**HOTEL, "hotelLink": "javascript:x"}]})
    )
    assert asyncio.run(bad.find(STAY)).url is None


def test_failed_hotel_source_passes_to_the_next() -> None:
    broken = TripComHotels(answer(404, text="gone"))
    working = TripComHotels(answer(200, {"hotelList": [HOTEL]}))

    assert asyncio.run(find_hotel([broken, working], STAY)).name == "Mock Palace"
    assert asyncio.run(find_hotel([broken], STAY)) is None


def test_exact_comes_from_the_source_or_the_flight_number_in_the_link() -> None:
    numbers = ["LH 623", "LH 1044"]
    deep = "https://www.lufthansa.com/d?FlightOut1=LH623&FlightOut2=LH1044"
    assert link_is_exact({"url": deep}, numbers)
    assert not link_is_exact({"url": "https://flights.gulfair.com/d?o=RUH"}, numbers)
    assert not link_is_exact({"url": deep, "specificity": "search_results"}, numbers)
    assert link_is_exact(
        {"url": "https://a.example", "specificity": "exact_flight"}, []
    )
    assert not link_is_exact({"url": deep}, [])


def test_link_choice_prefers_the_flight_then_the_airline_then_the_price() -> None:
    def link(url: str, kind: str, amount: int) -> dict:
        return {
            "url": url,
            "provider_type": kind,
            "price": {"amount": amount, "currency": "SAR"},
        }

    both = ["outbound", "inbound"]
    options = [
        {
            "legs": both,
            "links": [
                link("https://agent.example/a", "third_party", 700),
                link("https://air.example/b", "airline", 900),
                link("https://air.example/GF1", "airline", 950),
            ],
        }
    ]
    directions = {"outbound", "inbound"}

    exact = pick_link(options, directions, QUERY, None, ["GF 1"])
    assert exact["url"] == "https://air.example/GF1"
    assert pick_link(options, directions, QUERY)["url"] == "https://air.example/b"


WIKI_PAGE = {"query": {"pages": {"1": {"pageimage": "Manama.jpg"}}}}
WIKI_FILE = {
    "query": {
        "pages": {
            "-1": {
                "imageinfo": [
                    {
                        "thumburl": "https://upload.wikimedia.org/manama.jpg",
                        "descriptionurl": "https://commons.wikimedia.org/wiki/File:M",
                        "extmetadata": {
                            "LicenseShortName": {"value": "CC BY-SA 4.0"},
                            "Artist": {"value": "<a href='x'>A. Person</a>"},
                        },
                    }
                ]
            }
        }
    }
}


def wiki(file_body=WIKI_FILE, page_body=WIKI_PAGE) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=page_body
            if request.url.params.get("prop") == "pageimages"
            else file_body,
        )

    return httpx.MockTransport(handler)


def test_city_photo_comes_with_its_credit_and_plain_text() -> None:
    image = asyncio.run(fetch_place_image("Manama", wiki()))

    assert image.url == "https://upload.wikimedia.org/manama.jpg"
    assert image.license == "CC BY-SA 4.0"
    assert image.artist == "A. Person"


def test_page_without_a_photo_or_a_licence_gives_no_photo() -> None:
    nothing = {"query": {"pages": {"1": {}}}}
    assert asyncio.run(fetch_place_image("X", wiki(page_body=nothing))) is None
    bare = {
        "query": {
            "pages": {"-1": {"imageinfo": [{"thumburl": "https://u.example/a.jpg"}]}}
        }
    }
    assert asyncio.run(fetch_place_image("X", wiki(bare))) is None


def test_photo_cache_remembers_a_photo_and_an_empty_answer(tmp_path) -> None:
    cache = ImageCache(tmp_path / "images.sqlite3", 3600)
    assert cache.get("Paris") == (False, None)
    image = PlaceImage(
        url="https://u.example/a.jpg",
        source_url="https://u.example/a",
        license="CC0",
    )
    cache.put("Paris", image)
    cache.put("Nowhere", None)
    assert cache.get("Paris") == (True, image)
    assert cache.get("Nowhere") == (True, None)


def test_photos_are_off_when_switched_off() -> None:
    settings = Settings(_env_file=None, place_images_enabled=False)
    assert asyncio.run(with_place_images([], settings)) == []
