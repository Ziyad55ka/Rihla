"""Google Hotels through SerpApi. All fakes: no request leaves the test."""

import asyncio
from copy import deepcopy
from datetime import date
from decimal import Decimal

import httpx2 as httpx
import pytest

from app.core.config import Settings
from app.core.proposal_settings import DEFAULT_BOOKING_DOMAINS
from app.services.serpapi_hotels import SerpApiHotels, pick_property, pick_seller
from app.services.source_policy import apply_source_policy
from app.services.travel_providers import live_hotel_providers
from app.services.tripcom_provider import HotelQuery
from tests.proposals.test_source_policy import saved

STAY = HotelQuery("Doha", date(2026, 11, 20), date(2026, 11, 24), "Qatar")

SEARCH = {
    "properties": [
        {
            "type": "vacation rental",
            "name": "Flat",
            "rate_per_night": {"extracted_lowest": 90},
        },
        {
            "type": "hotel",
            "name": "Souq Hotel",
            "link": "https://souq.example/",
            "rate_per_night": {"extracted_lowest": 410},
            "property_token": "tok",
        },
    ]
}
DETAILS = {
    "featured_prices": [
        {
            "source": "Agoda",
            "link": "https://agoda.example/x",
            "rate_per_night": {"extracted_lowest": 395},
        },
        {
            "source": "Booking.com",
            "link": "https://booking.example/x",
            "rate_per_night": {"extracted_lowest": 420},
        },
    ]
}


def transport(seen: list[dict]):
    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        seen.append(params)
        return httpx.Response(
            200, json=DETAILS if "property_token" in params else SEARCH
        )

    return httpx.MockTransport(handler)


def test_off_without_a_key_and_on_with_one() -> None:
    assert live_hotel_providers(Settings(_env_file=None)) == []
    on = Settings(_env_file=None, serpapi_api_key="k")
    assert [item.name for item in live_hotel_providers(on)] == ["serpapi"]


def test_prefers_booking_com_price_and_link_in_sar() -> None:
    seen: list[dict] = []
    offer = asyncio.run(SerpApiHotels("k", transport=transport(seen)).find(STAY))

    assert offer is not None
    assert offer.name == "Souq Hotel"
    assert offer.price_sar == Decimal("420.00")
    assert offer.url == "https://booking.example/x"
    assert offer.source.startswith("Booking.com")
    assert offer.exact_price is True
    first = seen[0]
    assert first["currency"] == "SAR" and first["gl"] == "sa"
    assert (first["check_in_date"], first["check_out_date"]) == (
        "2026-11-20",
        "2026-11-24",
    )
    assert "Qatar" in first["q"]


def test_without_details_uses_the_search_price_and_hotel_link() -> None:
    seen: list[dict] = []
    offer = asyncio.run(
        SerpApiHotels("k", details=False, transport=transport(seen)).find(STAY)
    )
    assert offer is not None and offer.price_sar == Decimal("410.00")
    assert offer.url == "https://souq.example/" and offer.exact_price is False
    assert len(seen) == 1


def test_price_source_is_google_even_when_navigation_link_is_a_hotel_website():
    body = deepcopy(SEARCH)
    source_url = "https://www.google.com/travel/search?q=Doha+hotels"
    body["search_metadata"] = {"google_hotels_url": source_url}
    provider = SerpApiHotels(
        "k",
        details=False,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)),
    )
    offer = asyncio.run(provider.find(STAY))
    assert offer.source_url == source_url
    assert offer.url == "https://souq.example/"
    proposal = saved(offer.source_url)
    result = apply_source_policy(proposal, list(DEFAULT_BOOKING_DOMAINS))
    assert result.cities[0].hotel_price_per_night.amount_sar is not None
    assert result.cities[0].hotel_name.value is not None


@pytest.mark.parametrize(
    "url",
    [
        "https://google.com.evil.test/travel/hotels",
        "https://www.google.com/search?q=hotel",
        "https://user:secret@www.google.com/travel/hotels",
        "http://www.google.com/travel/hotels",
    ],
)
def test_untrusted_source_metadata_cannot_bypass_source_policy(url):
    body = deepcopy(SEARCH)
    body["search_metadata"] = {"google_hotels_url": url}
    provider = SerpApiHotels(
        "k",
        details=False,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)),
    )
    assert asyncio.run(provider.find(STAY)).source_url is None


def test_errors_and_empty_results_give_no_offer() -> None:
    def failing(request):
        return httpx.Response(500, json={})

    hotels = SerpApiHotels("k", transport=httpx.MockTransport(failing))
    assert asyncio.run(hotels.find(STAY)) is None
    assert pick_property({"properties": []}) is None
    assert pick_seller({"prices": [{"source": "X", "link": "http://insecure"}]}) is None


def test_hotel_ad_link_uses_the_observed_price_page_without_losing_the_quote():
    body = deepcopy(SEARCH)
    body["properties"][1]["link"] = "https://www.google.com/aclk?adurl"
    source_url = "https://www.google.com/travel/search?q=Doha+hotels"
    body["search_metadata"] = {"google_hotels_url": source_url}
    provider = SerpApiHotels(
        "k",
        details=False,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body)),
    )
    offer = asyncio.run(provider.find(STAY))
    assert offer is not None
    assert offer.name == "Souq Hotel" and offer.price_sar == Decimal("410.00")
    assert offer.url == source_url and offer.exact_price is False


def test_a_seller_ad_redirect_cannot_become_an_exact_booking_quote():
    details = deepcopy(DETAILS)
    for item in details["featured_prices"]:
        item["link"] = "https://www.google.com/aclk?adurl"
    assert pick_seller(details) is None


def test_cheapest_seller_when_booking_com_is_not_listed() -> None:
    details = {
        "prices": [
            {
                "source": "A",
                "link": "https://a.example",
                "rate_per_night": {"extracted_lowest": 500},
            },
            {
                "source": "B",
                "link": "https://b.example",
                "rate_per_night": {"extracted_lowest": 450},
            },
        ]
    }
    assert pick_seller(details) == ("B", Decimal("450.00"), "https://b.example")


def test_an_older_env_that_lists_only_tripcom_still_uses_the_key() -> None:
    old = Settings(_env_file=None, serpapi_api_key="k", hotel_providers=["tripcom"])
    assert [item.name for item in live_hotel_providers(old)] == ["serpapi"]
