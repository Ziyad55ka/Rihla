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
) -> ExtractedFact:
    return ExtractedFact(
        field_id=field_id,
        value=value,
        amount=amount,
        currency=currency,
        status=status,
        source_id=source_id,
        quote=quote,
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

    assert len(plan) == 1
    assert not any("how to travel" in group.query for group in plan)


def test_multi_city_plan_searches_each_needed_subject() -> None:
    plan = build_search_plan(request_for("Tbilisi", "Batumi"))

    assert len(plan) == 3
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
    async def no_sources(query, settings, cost=None):
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


def test_usd_price_stays_internal_and_is_not_available_in_sar() -> None:
    fact = extracted(
        amount=320, currency="USD", quote="Average flight fares start at $320."
    )

    result = verify_field(PRICE, fact, [SOURCE])

    assert result.unavailable_reason == "no_sar_conversion"
    assert (result.source_amount, result.source_currency) == (Decimal("320"), "USD")
    assert result.source_evidence[0].quote == "Average flight fares start at $320."
    public = to_sar_price(result)
    assert (public.amount_sar, public.status) == (None, "Not available")


def test_sar_price_is_shown_but_never_confirmed() -> None:
    fact = extracted(
        amount=1200,
        currency="SAR",
        status="Confirmed",
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
        status="Confirmed",
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
