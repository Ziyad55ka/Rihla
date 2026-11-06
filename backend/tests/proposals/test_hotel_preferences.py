import asyncio
from dataclasses import replace

import httpx2 as httpx
import pytest

from app.services.accommodation_preferences import (
    group_hotel_stars,
    parse_stars,
    readable,
)
from app.services.proposal_generation import GenerationBlocked, collect_requirements
from app.services.serpapi_hotels import SerpApiHotels, average_offer
from tests.proposals.test_proposal_generation import group
from tests.proposals.test_serpapi_hotels import STAY


def test_private_encoding_legacy_and_explicit_lower_classes():
    assert parse_stars("stay:stars=5;lower=3,4;notes:Near metro") == (3, 4, 5)
    assert parse_stars("stay:stars=4;lower=5;notes:") == (4,)
    assert parse_stars("Step-free hotel") is None
    assert (
        readable("stay:stars=5;lower=4;notes:Near metro")
        == "Hotel class: 4, 5 stars only. Near metro"
    )


def test_shared_hotel_requires_common_allowed_class():
    generation = group(
        accommodation={"value": "stay:stars=5;lower=;notes:", "importance": "Essential"}
    )
    generation.members[1].accommodation.value = "stay:stars=4;lower=3;notes:"
    assert group_hotel_stars(generation) == ((), True)
    with pytest.raises(GenerationBlocked):
        collect_requirements(generation)
    generation.members[0].accommodation.value = "stay:stars=5;lower=4;notes:"
    assert group_hotel_stars(generation) == ((4,), True)


def test_fallback_keeps_stars_and_rejects_review_rating_as_hotel_class():
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(
            200,
            json={
                "properties": [
                    {
                        "type": "hotel",
                        "name": "Wrong",
                        "overall_rating": 5,
                        "extracted_hotel_class": 3,
                        "link": "https://example.test/hotel",
                        "rate_per_night": {"extracted_lowest": 200},
                    }
                ]
            },
        )

    query = replace(STAY, stars=(5,), strict_stars=True)
    assert (
        asyncio.run(
            SerpApiHotels("fake", transport=httpx.MockTransport(handler)).find(query)
        )
        is None
    )
    assert len(seen) == 3 and all(p["hotel_class"] == "5" for p in seen)


def test_average_is_dated_tax_inclusive_and_does_not_name_a_hotel():
    query = replace(STAY, stars=(4,), strict_stars=True)
    body = {
        "search_metadata": {
            "google_hotels_url": "https://www.google.com/travel/search?q=hotels"
        },
        "properties": [
            {
                "extracted_hotel_class": stars,
                "rate_per_night": {
                    "extracted_lowest": low,
                    "extracted_after_taxes_fees": tax,
                },
            }
            for stars, low, tax in [(4, 100, 120), (4, 200, 240), (3, 20, 30)]
        ],
    }
    offer = average_offer(body, query)
    assert offer and offer.price_sar == 180 and offer.average_sample_size == 2
    assert not offer.exact_price and offer.source == "Google Hotels market average"


def test_malformed_and_invalid_hotel_rates_are_not_zero_quotes():
    from app.services.serpapi_hotels import pick_property

    for rate in [
        [],
        "bad",
        {"extracted_lowest": "NaN"},
        {"extracted_lowest": "Infinity"},
        {"extracted_lowest": "1e999"},
        {"extracted_lowest": "0.001"},
    ]:
        assert (
            pick_property(
                {"properties": [None, "bad", {"name": "Hotel", "rate_per_night": rate}]}
            )
            is None
        )


def test_essential_class_needs_a_verified_hotel_class_not_a_model_claim(
    tmp_path, monkeypatch
):
    from app.services import proposal_generation, trip_research
    from app.services.trip_research import ResearchCost
    from tests.proposals.test_proposal_generation import fake_research, option, settings

    generation = group(
        accommodation={"value": "stay:stars=5;lower=;notes:", "importance": "Essential"}
    )

    async def research(request, config):
        assert request.hotel_stars == (5,) and request.strict_hotel_stars
        result = await fake_research()(request, config)
        result.hotel_stars = {0: 4}
        return result

    monkeypatch.setattr(trip_research, "research", research)
    with pytest.raises(proposal_generation.OptionRejected) as failure:
        asyncio.run(
            proposal_generation._research_option(
                option("Paris"),
                1,
                generation,
                [],
                [],
                ["Riyadh"],
                1,
                settings(tmp_path),
                ResearchCost(),
            )
        )
    assert failure.value.reasons == ["essential_not_met"]
