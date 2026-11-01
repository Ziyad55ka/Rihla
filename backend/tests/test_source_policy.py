"""Stay names and prices come from approved booking sites only."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from app.schemas.proposals import (
    CityStay,
    Evidence,
    InfoField,
    Proposal,
    ProposalSource,
    SarPrice,
)
from app.services.source_policy import apply_source_policy, classify_source
from app.services.trip_research import (
    ExtractedFact,
    FieldSpec,
    ResearchRequest,
    ResearchSource,
    build_search_plan,
    verify_field,
)

DOMAINS = ["booking.com", "agoda.com"]
BLOG = ResearchSource(
    id=1,
    title="Best hotels",
    url="https://jetmeaway.co.uk/blog/manama",
    content="Oriental Palace Hotel is from £36/night.",
)
BOOKING = ResearchSource(
    id=2,
    title="Hotels",
    url="https://www.booking.com/city/bh/manama.html",
    content="Oriental Palace Hotel is from £36/night.",
)
NAME = FieldSpec("cities.0.hotel_name", "hotel_name", "A hotel", "text")
PRICE = FieldSpec("cities.0.hotel_price_per_night", "hotel_price", "Price", "price")


def name_fact(source_id: int) -> ExtractedFact:
    return ExtractedFact(
        field_id=NAME.id,
        value="Oriental Palace Hotel",
        amount=None,
        currency=None,
        status="Sourced",
        source_id=source_id,
        quote="Oriental Palace Hotel is from £36/night.",
        estimate_sar=None,
    )


def price_fact(source_id: int) -> ExtractedFact:
    return ExtractedFact(
        field_id=PRICE.id,
        value=None,
        amount=36,
        currency="GBP",
        status="Estimated",
        source_id=source_id,
        quote="Oriental Palace Hotel is from £36/night.",
        estimate_sar=500,
    )


def test_sources_are_classified_by_domain() -> None:
    assert classify_source("https://www.booking.com/x", "T", DOMAINS) == "booking"
    assert classify_source("https://sub.agoda.com/x", "T", DOMAINS) == "booking"
    assert classify_source("https://notbooking.com/x", "T", DOMAINS) == "ideas"
    assert classify_source("https://tripadvisor.com/x", "T", DOMAINS) == "ideas"
    assert (
        classify_source("https://a.com", "Ignav booking link: A", DOMAINS) == "flight"
    )


def test_hotel_from_an_article_alone_is_not_shown() -> None:
    result = verify_field(NAME, name_fact(1), [BLOG], DOMAINS)

    assert result.status == "Not available"
    assert result.unavailable_reason == "rejected_not_booking_source"


def test_hotel_from_booking_is_shown() -> None:
    result = verify_field(NAME, name_fact(2), [BOOKING], DOMAINS)

    assert result.value == "Oriental Palace Hotel"


def test_price_from_a_blog_is_rejected_with_no_general_estimate() -> None:
    result = verify_field(PRICE, price_fact(1), [BLOG], DOMAINS)

    assert result.status == "Not available"
    assert result.amount_sar is None


def test_price_from_booking_is_an_estimate() -> None:
    result = verify_field(PRICE, price_fact(2), [BOOKING], DOMAINS)

    assert result.status == "Estimated"
    assert result.amount_sar == Decimal("180.72")


def test_hotel_search_stays_close_to_the_old_tavily_count() -> None:
    plan = build_search_plan(
        ResearchRequest(destination="France", cities=["Paris", "Lyon"], period="May")
    )

    assert sum(group.booking_only for group in plan) == 2
    # Two hotel searches, one transfer, and a single shared ideas search.
    assert len(plan) == 4
    assert all("price" in group.query for group in plan if group.booking_only)


def saved(url: str, hotel_status="Sourced") -> Proposal:
    evidence = [Evidence(source_id=1, quote="q")]
    return Proposal(
        id=UUID("00000000-0000-4000-8000-0000000000bb"),
        trip_id=UUID("00000000-0000-4000-8000-0000000000aa"),
        version=1,
        option_number=1,
        title="T",
        destination="Bahrain",
        start_date=date(2026, 11, 20),
        end_date=date(2026, 11, 21),
        cities=[
            CityStay(
                order=1,
                city="Manama",
                nights=1,
                hotel_name=InfoField(
                    value="Palace", status=hotel_status, evidence=evidence
                ),
                hotel_price_per_night=SarPrice(
                    amount_sar="180", status="Estimated", evidence=evidence
                ),
                booking_url=(
                    "https://www.booking.com/searchresults.html?"
                    "ss=Palace%2C+Manama%2C+Bahrain&group_adults=1"
                ),
            )
        ],
        flights=[],
        intercity_transport=[],
        flexible_adjustments=[],
        budget_status="within_group_budget",
        sources=[ProposalSource(id=1, title="Guide", url=url)],
    )


def test_older_proposal_from_a_blog_shows_a_city_search_only() -> None:
    result = apply_source_policy(saved("https://jetmeaway.co.uk/x"), DOMAINS)
    stay = result.cities[0]

    assert stay.hotel_name.status == "Not available"
    assert stay.hotel_price_per_night.status == "Not available"
    assert "Palace" not in stay.booking_url
    assert "Manama" in stay.booking_url and "group_adults=1" in stay.booking_url
    assert result.budget_status == "includes_unconfirmed"
    assert result.sources[0].kind == "ideas"


def test_older_proposal_from_booking_is_unchanged() -> None:
    result = apply_source_policy(saved("https://www.booking.com/x"), DOMAINS)

    assert result.cities[0].hotel_name.value == "Palace"
    assert result.budget_status == "within_group_budget"
    assert result.sources[0].kind == "booking"
