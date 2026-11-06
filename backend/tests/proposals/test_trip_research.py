import asyncio
import logging
from decimal import Decimal
from pathlib import Path

import httpx2 as httpx
import pytest

from app.core.config import Settings
from app.services import trip_research
from app.services.trip_research import (
    ExtractedFact,
    FieldSpec,
    ResearchError,
    ResearchRequest,
    ResearchSource,
    build_search_plan,
    describes_other_country,
    research,
    search_sources,
    to_sar_price,
    verify_field,
)

SOURCE = ResearchSource(
    id=1,
    title="Istanbul guide",
    url="https://example.com/istanbul",
    content=(
        "Flights from Riyadh take about 5 hours. "
        "Average flight fares start at $320. "
        "Flight fares from SAR 1,200 are common. "
        "The museum has 320 paintings. "
        "Mock Hotel rooms cost SAR 450 per night."
    ),
)
DURATION = FieldSpec(
    "flights.duration", "flight_duration", "Duration", "duration", ("flight",)
)
PRICE = FieldSpec(
    "flights.price_per_person", "flight_price", "Price", "price", ("flight|fare",)
)
HOTEL = FieldSpec("cities.0.hotel_name", "hotel_name", "Hotel", "text")


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        tavily_api_key="test-key",
        search_cache_db=tmp_path / "cache.sqlite3",
    )


def extracted(
    field_id: str = "x",
    value: str | None = None,
    amount: float | None = None,
    currency: str | None = None,
    status: str = "Estimated",
    source_id: int | None = 1,
    quote: str | None = None,
    estimate_sar: float | None = None,
) -> ExtractedFact:
    return ExtractedFact(
        field_id=field_id,
        value=value,
        amount=amount,
        currency=currency,
        status=status,
        source_id=source_id,
        quote=quote,
        estimate_sar=estimate_sar,
    )


def transport_returning(
    response: httpx.Response, calls: list[httpx.Request]
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return response

    return httpx.MockTransport(handler)


def results_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "results": [
                {"title": SOURCE.title, "url": SOURCE.url, "content": SOURCE.content},
                {"title": "Bad", "url": "ftp://example.com", "content": "x"},
            ],
            "usage": {"credits": 1},
        },
    )


def request_for(*cities: str) -> ResearchRequest:
    return ResearchRequest(
        destination="Georgia", cities=list(cities), period="late November"
    )


def test_single_city_plan_skips_transfer_search() -> None:
    plan = build_search_plan(request_for("Istanbul"))

    # One ideas search, then one limited to booking sites.
    assert len(plan) == 2
    assert [group.booking_only for group in plan] == [False, True]
    assert not any("how to travel" in group.query for group in plan)


def test_multi_city_plan_searches_each_needed_subject() -> None:
    plan = build_search_plan(request_for("Tbilisi", "Batumi"))

    assert len(plan) == 4
    assert any("from Tbilisi to Batumi" in group.query for group in plan)


def test_search_uses_basic_depth_counts_credits_and_caches(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    calls: list[httpx.Request] = []
    transport = transport_returning(results_response(), calls)
    cost = trip_research.ResearchCost()

    first, first_cached = asyncio.run(
        search_sources("Istanbul", settings, transport, cost)
    )
    second, second_cached = asyncio.run(
        search_sources("  ISTANBUL ", settings, transport, cost)
    )

    assert len(calls) == 1
    assert b'"search_depth":"basic"' in calls[0].content.replace(b" ", b"")
    assert calls[0].headers["Authorization"] == "Bearer test-key"
    assert [source.url for source in first] == [SOURCE.url]
    assert second == first
    assert (first_cached, second_cached) == (False, True)
    assert (cost.tavily_credits, cost.cached_searches) == (1, 1)


def test_expired_cache_searches_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = make_settings(tmp_path)
    calls: list[httpx.Request] = []
    transport = transport_returning(results_response(), calls)
    asyncio.run(search_sources("Istanbul", settings, transport))

    now = trip_research.time.time()
    monkeypatch.setattr(trip_research.time, "time", lambda: now + 25 * 3600)
    asyncio.run(search_sources("Istanbul", settings, transport))

    assert len(calls) == 2


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "search_auth"),
        (429, "search_quota"),
        (432, "search_quota"),
        (433, "search_quota"),
        (500, "search_unavailable"),
    ],
)
def test_search_failures_have_clear_codes_and_hide_the_key(
    tmp_path: Path, status: int, code: str
) -> None:
    transport = transport_returning(
        httpx.Response(status, headers={"Retry-After": "7"}), []
    )

    with pytest.raises(ResearchError) as caught:
        asyncio.run(search_sources("Istanbul", make_settings(tmp_path), transport))

    assert caught.value.code == code
    assert "test-key" not in caught.value.message
    assert caught.value.retry_after == ("7" if status == 429 else None)


def test_network_failure_is_reported(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(ResearchError) as caught:
        asyncio.run(
            search_sources(
                "Istanbul", make_settings(tmp_path), httpx.MockTransport(handler)
            )
        )

    assert caught.value.code == "search_unavailable"


def test_missing_key_stops_before_any_request(tmp_path: Path) -> None:
    settings = make_settings(tmp_path).model_copy(update={"tavily_api_key": None})

    with pytest.raises(ResearchError) as caught:
        asyncio.run(search_sources("Istanbul", settings))

    assert caught.value.code == "not_configured"


def test_no_results_does_not_spend_a_gemini_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def no_sources(query, settings, cost=None, include_domains=None):
        return [], False

    async def fail_if_called(groups, settings, cost):
        raise AssertionError("Gemini must not be called")

    monkeypatch.setattr(trip_research, "search_sources", no_sources)
    monkeypatch.setattr(trip_research, "extract_facts", fail_if_called)

    with pytest.raises(ResearchError) as caught:
        asyncio.run(research(request_for("Istanbul"), make_settings(tmp_path)))

    assert caught.value.code == "no_results"


def test_supported_duration_keeps_its_quote() -> None:
    quote = "Flights from Riyadh take about 5 hours."
    result = verify_field(
        DURATION, extracted(value="about 5 hours", quote=quote), [SOURCE]
    )

    assert result.value == "about 5 hours"
    assert result.evidence[0].quote == quote
    assert result.unavailable_reason is None


def test_absent_and_unextracted_are_told_apart() -> None:
    empty = SOURCE.model_copy(update={"content": "A page about the weather."})

    assert verify_field(DURATION, None, [empty]).unavailable_reason == (
        "absent_from_search"
    )
    assert verify_field(DURATION, None, [SOURCE]).unavailable_reason == "not_extracted"


@pytest.mark.parametrize(
    ("fact", "reason"),
    [
        (
            extracted(value="about 5 hours", quote="Takes 5 hours by flight."),
            "rejected_quote_not_in_source",
        ),
        (
            extracted(
                value="about 5 hours",
                source_id=99,
                quote="Flights from Riyadh take about 5 hours.",
            ),
            "rejected_unknown_source",
        ),
        (
            extracted(
                value="about 9 hours",
                quote="Flights from Riyadh take about 5 hours.",
            ),
            "rejected_value_not_in_quote",
        ),
    ],
)
def test_bad_evidence_is_rejected_with_a_reason(
    fact: ExtractedFact, reason: str
) -> None:
    result = verify_field(DURATION, fact, [SOURCE])

    assert result.value is None
    assert result.status == "Not available"
    assert result.unavailable_reason == reason


def test_matching_number_about_another_subject_is_rejected() -> None:
    fact = extracted(amount=320, currency="USD", quote="The museum has 320 paintings.")

    result = verify_field(PRICE, fact, [SOURCE])

    assert result.unavailable_reason == "rejected_wrong_topic"


def test_invented_hotel_name_is_rejected() -> None:
    fact = extracted(
        value="Other Hotel", quote="Mock Hotel rooms cost SAR 450 per night."
    )

    result = verify_field(HOTEL, fact, [SOURCE])

    assert result.unavailable_reason == "rejected_value_not_in_quote"


def test_usd_price_is_converted_as_estimated_and_keeps_the_original() -> None:
    fact = extracted(
        amount=320,
        currency="USD",
        status="Unconfirmed",
        quote="Average flight fares start at $320.",
    )

    result = verify_field(PRICE, fact, [SOURCE])

    assert (result.source_amount, result.source_currency) == (Decimal("320.0"), "USD")
    public = to_sar_price(result)
    assert (public.amount_sar, public.status) == (Decimal("1200.00"), "Estimated")
    assert "source_amount" not in public.model_dump()
    assert public.evidence[0].quote == "Average flight fares start at $320."


def test_every_table_currency_has_a_marker_and_usd_is_the_peg() -> None:
    assert set(trip_research.SAR_PER_UNIT) <= set(trip_research.CURRENCY_MARKERS)
    assert trip_research.SAR_PER_UNIT["USD"] == Decimal("3.75")


def test_currency_outside_the_table_is_not_available() -> None:
    source = SOURCE.model_copy(update={"content": "Flight fares start at JPY 9000."})
    fact = extracted(
        amount=9000, currency="JPY", quote="Flight fares start at JPY 9000."
    )

    result = verify_field(PRICE, fact, [source])

    assert result.unavailable_reason == "no_sar_conversion"
    assert (result.source_amount, result.source_currency) == (Decimal("9000.0"), "JPY")
    assert result.source_evidence[0].quote == "Flight fares start at JPY 9000."
    public = to_sar_price(result)
    assert (public.amount_sar, public.status) == (None, "Not available")


def test_sar_price_is_shown_but_never_confirmed() -> None:
    fact = extracted(
        amount=1200,
        currency="SAR",
        status="Sourced",
        quote="Flight fares from SAR 1,200 are common.",
    )

    public = to_sar_price(verify_field(PRICE, fact, [SOURCE]))

    assert public.amount_sar == Decimal("1200.0")
    assert public.status == "Estimated"


def test_currency_must_appear_in_the_quote() -> None:
    fact = extracted(
        amount=320, currency="SAR", quote="Average flight fares start at $320."
    )

    result = verify_field(PRICE, fact, [SOURCE])

    assert result.unavailable_reason == "rejected_currency_unverified"


def test_quote_shared_by_sources_cannot_stay_confirmed() -> None:
    copy = SOURCE.model_copy(update={"id": 2, "url": "https://example.com/copy"})
    fact = extracted(
        value="Mock Hotel",
        status="Sourced",
        quote="Mock Hotel rooms cost SAR 450 per night.",
    )

    result = verify_field(HOTEL, fact, [SOURCE, copy])

    assert result.status == "Unconfirmed"
    assert result.shared_quote is True


def test_logs_hold_only_category_and_reason(caplog: pytest.LogCaptureFixture) -> None:
    fact = extracted(
        value="Secret Hotel", quote="Mock Hotel rooms cost SAR 450 per night."
    )

    with caplog.at_level(logging.INFO, logger="app.services.trip_research"):
        verify_field(HOTEL, fact, [SOURCE])

    assert caplog.messages == [
        "research_field category=hotel_name reason=rejected_value_not_in_quote"
    ]


def test_plan_searches_each_departure_city_once() -> None:
    request = request_for("Istanbul").model_copy(
        update={"origins": ["Riyadh", " riyadh ", "Jeddah"]}
    )

    queries = [group.query for group in build_search_plan(request)]

    assert sum(query.startswith("flights from") for query in queries) == 2
    assert any("from Jeddah to" in query for query in queries)


def test_sources_are_ranked_and_blocked_sites_removed(tmp_path: Path) -> None:
    def result(url: str) -> dict:
        return {"title": "T", "url": url, "content": "C"}

    response = httpx.Response(
        200,
        json={
            "results": [
                result("https://www.easemytrip.com/flights"),
                result("https://www.youtube.com/watch?v=1"),
                result("https://example.com/guide"),
                result("https://www.booking.com/city/tr/istanbul.html"),
                result("https://notyoutube.com/page"),
            ]
        },
    )
    calls: list[httpx.Request] = []

    found, _ = asyncio.run(
        search_sources(
            "Istanbul", make_settings(tmp_path), transport_returning(response, calls)
        )
    )

    assert [source.url for source in found] == [
        "https://www.booking.com/city/tr/istanbul.html",
        "https://example.com/guide",
        "https://notyoutube.com/page",
        "https://www.easemytrip.com/flights",
    ]
    assert b"youtube.com" in calls[0].content


def source_titled(title: str, url: str = "https://example.com/x") -> ResearchSource:
    return ResearchSource(id=1, title=title, url=url, content="c")


def test_city_searches_name_the_country() -> None:
    request = ResearchRequest(
        destination="Egypt",
        country="Egypt",
        cities=["Cairo", "Alexandria"],
        period="December 2026",
    )

    queries = [group.query for group in build_search_plan(request)]

    assert any("hotels in Alexandria, Egypt" in query for query in queries)
    assert any("from Cairo to Alexandria, Egypt" in query for query in queries)


@pytest.mark.parametrize(
    ("source", "other"),
    [
        (source_titled("16 Best Hotels in Alexandria, Virginia"), True),
        (source_titled("Hotels", "https://x.com/us/alexandria-virginia/"), True),
        (source_titled("Best Hotels in Alexandria, Egypt"), False),
        (source_titled("Best Hotels in Alexandria"), False),
        (source_titled("Egypt and Jordan compared"), False),
    ],
)
def test_sources_about_another_country_are_detected(
    source: ResearchSource, other: bool
) -> None:
    assert describes_other_country(source, "Egypt") is other


def test_turkey_alias_is_not_another_country() -> None:
    assert not describes_other_country(source_titled("Hotels in Türkiye"), "Turkey")


def test_quote_listing_many_airlines_is_unconfirmed() -> None:
    spec = FieldSpec("flights.0.airline", "flight_airline", "Airline", "text")
    source = SOURCE.model_copy(update={"content": "EgyptAir Saudia Flynas Nile Air"})
    fact = extracted(
        value="EgyptAir", status="Sourced", quote="EgyptAir Saudia Flynas Nile Air"
    )

    assert verify_field(spec, fact, [source]).status == "Unconfirmed"


def test_quote_naming_one_airline_stays_sourced() -> None:
    spec = FieldSpec("flights.0.airline", "flight_airline", "Airline", "text")
    source = SOURCE.model_copy(update={"content": "Saudia flies this route daily."})
    fact = extracted(
        value="Saudia", status="Sourced", quote="Saudia flies this route daily."
    )

    assert verify_field(spec, fact, [source]).status == "Sourced"


@pytest.mark.parametrize("amount", [630, 1800])
def test_price_range_uses_the_upper_bound(amount: int) -> None:
    quote = "Typical flight price: SAR 630–1,800."
    source = SOURCE.model_copy(update={"content": quote})
    fact = extracted(amount=amount, currency="SAR", status="Sourced", quote=quote)

    public = to_sar_price(verify_field(PRICE, fact, [source]))

    assert public.amount_sar == Decimal("1800")
    assert public.status == "Estimated"


@pytest.mark.parametrize(
    ("amount", "currency", "quote", "expected"),
    [
        (116, "EUR", "Prices begin at 116 € at the Mock Hotel.", "486.04"),
        (158, "USD", "With an average room price of just $158.", "592.50"),
        (450, "SAR", "Rooms from SAR 450 per night.", "450"),
    ],
)
def test_hotel_prices_from_sources_are_accepted_as_estimated(
    amount: int, currency: str, quote: str, expected: str
) -> None:
    spec = FieldSpec(
        "cities.0.hotel_price_per_night",
        "hotel_price",
        "Price",
        "price",
        (trip_research.NIGHT_TOPIC,),
    )
    source = SOURCE.model_copy(update={"content": quote})
    fact = extracted(amount=amount, currency=currency, status="Sourced", quote=quote)

    public = to_sar_price(verify_field(spec, fact, [source]))

    assert public.amount_sar == Decimal(expected)
    assert public.status == "Estimated"


def test_price_with_no_evidence_uses_the_estimate_as_unconfirmed() -> None:
    fact = extracted(status="Not available", source_id=None, estimate_sar=350)

    public = to_sar_price(verify_field(PRICE, fact, [SOURCE]))

    assert public.amount_sar == Decimal("350.00")
    assert public.status == "Unconfirmed"
    assert public.evidence == []


def test_estimate_replaces_a_rejected_quote_without_keeping_it() -> None:
    fact = extracted(
        amount=900, currency="SAR", quote="Not in the source.", estimate_sar=700
    )

    public = to_sar_price(verify_field(PRICE, fact, [SOURCE]))

    assert (public.amount_sar, public.status) == (Decimal("700.00"), "Unconfirmed")


def test_estimate_is_not_used_for_text_or_absurd_values() -> None:
    fact = extracted(status="Not available", source_id=None, estimate_sar=350)
    absurd = extracted(status="Not available", source_id=None, estimate_sar=5e9)

    assert verify_field(HOTEL, fact, [SOURCE]).value is None
    assert verify_field(PRICE, absurd, [SOURCE]).amount_sar is None


def test_live_hotels_skip_their_web_search_and_fill_the_city(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import date as day
    from decimal import Decimal as Dec

    from app.services.tripcom_provider import HotelOffer

    queries: list[str] = []

    async def sources(query, settings, cost=None, include_domains=None):
        queries.append(query)
        return [
            SOURCE.model_copy(update={"url": f"https://ex.example/{len(queries)}"})
        ], False

    async def facts(groups, settings, cost):
        return []

    class Hotels:
        name = "fake"

        async def find(self, query):
            return HotelOffer(
                "Souq Hotel",
                Dec("420.00"),
                "https://booking.example/x",
                "Booking.com via Google",
                exact_price=True,
                source_url="https://www.google.com/travel/search?q=Souq+Hotel",
            )

    monkeypatch.setattr(trip_research, "search_sources", sources)
    monkeypatch.setattr(trip_research, "extract_facts", facts)
    monkeypatch.setattr(trip_research, "live_hotel_providers", lambda s: [Hotels()])
    request = request_for("Doha").model_copy(
        update={
            "departure_date": day(2026, 12, 1),
            "return_date": day(2026, 12, 5),
            "nights": [4],
        }
    )

    result = asyncio.run(research(request, make_settings(tmp_path)))

    assert not any("hotels in" in query for query in queries)
    by_id = {item.field_id: item for item in result.fields}
    assert by_id["cities.0.hotel_name"].value == "Souq Hotel"
    assert by_id["cities.0.hotel_price_per_night"].amount_sar == Dec("420.00")
    assert result.hotel_links == {0: "https://booking.example/x"}
    hotel_source = next(s for s in result.sources if "Souq Hotel" in s.title)
    assert hotel_source.url == "https://www.google.com/travel/search?q=Souq+Hotel"


def test_extraction_uses_low_thinking_and_the_planner_keeps_the_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[dict] = []

    async def fake(payload, prompt, schema, settings, cost, **kwargs):
        seen.append(kwargs)
        return schema.model_validate({"facts": []})

    monkeypatch.setattr(trip_research, "call_gemini", fake)
    asyncio.run(
        trip_research.extract_facts(
            [], make_settings(tmp_path), trip_research.ResearchCost()
        )
    )
    assert seen == [{"thinking": "low"}]
