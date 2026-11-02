"""Settings for AI proposals and flight checks, apart from the Sprint 1 ones."""

from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings

BACKEND_DIR = Path(__file__).resolve().parents[2]
LOCAL_DIR = BACKEND_DIR / ".local"

DEFAULT_BOOKING_DOMAINS = (
    "booking.com",
    "agoda.com",
    "expedia.com",
    "hotels.com",
    "airbnb.com",
    "marriott.com",
    "hilton.com",
    "ihg.com",
    "accor.com",
    "hyatt.com",
    # Price sources. The booking button stays Booking.com.
    "kayak.com",
    "momondo.com",
    "trivago.com",
    # Google Hotels only, not the rest of Google.
    "google.com/travel",
    # Off unless TRIPCOM_ENABLED. Listed so its own hotels count as a price source.
    "trip.com",
)


class ProposalSettings(BaseSettings):
    # Bypasses Row Level Security. Used only by services/generation_inputs.py.
    supabase_secret_key: str | None = Field(default=None, repr=False)
    # Keys the stored inputs hash, so budgets cannot be guessed from it.
    proposals_hash_key: str | None = Field(default=None, repr=False)
    # Serve saved proposals instead of calling Gemini, Tavily and Ignav.
    proposals_demo_mode: bool = False
    proposals_demo_file: Path = BACKEND_DIR / "app" / "data" / "demo_proposals.json"
    # Below this per trip day, generation stops before any outside request.
    min_budget_sar_per_day: Decimal = Field(default=Decimal(250), gt=0)
    # Where finished generations are remembered, and for how long they are reused.
    generation_store_db: Path = LOCAL_DIR / "generations.sqlite3"
    saved_proposals_ttl_hours: int = Field(default=24, ge=1)
    # Generation stops here and returns the proposals that already passed.
    max_gemini_calls_per_generation: int = Field(default=7, ge=1)

    # Gemini writes the plan and reads the search results.
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3-flash-preview"
    gemini_retry_delay_seconds: float = Field(default=20, ge=0)
    # Tavily searches the web. Results are cached to save the free credits.
    tavily_api_key: str | None = None
    tavily_search_depth: Literal["basic", "advanced"] = "basic"
    tavily_max_results: int = Field(default=5, ge=1, le=20)
    search_cache_db: Path = LOCAL_DIR / "search-cache.sqlite3"
    search_cache_ttl_hours: int = Field(default=24, ge=1)

    # ignav: live fares, falling back to web search. tavily: web search only.
    flight_price_provider: Literal["ignav", "tavily"] = "ignav"
    ignav_api_key: str | None = None
    # An Ignav amount covers the whole party: tested with 1 and 2 adults, 1 Nov 2026.
    ignav_price_scope: Literal["per_person", "total"] = "total"
    # Sources in the order they are preferred. Only sources switched on are asked.
    flight_providers: list[str] = Field(default_factory=lambda: ["tripcom", "ignav"])
    hotel_providers: list[str] = Field(default_factory=lambda: ["tripcom"])
    # Academic use only. Read docs/ai-proposals.md before switching this on.
    tripcom_enabled: bool = False

    # A split trip must save this much, and may take only this much longer.
    split_min_saving_percent: Decimal = Field(default=Decimal(15), ge=0, lt=100)
    split_max_extra_duration_percent: Decimal = Field(default=Decimal(30), ge=0)
    # Fares reused by generation only. Refresh and book always ask the sources.
    flight_cache_minutes: int = Field(default=15, ge=0)
    # Limits, all to protect the free requests.
    member_flight_actions_per_hour: int = Field(default=5, ge=0)
    trip_requests_per_day: int = Field(default=30, ge=0)
    daily_requests_per_source: int = Field(default=200, ge=0)
    flight_usage_db: Path = LOCAL_DIR / "flight-usage.sqlite3"
    # How long a flight button stays off after each press.
    refresh_cooldown_minutes: int = Field(default=2, ge=0)
    # Ignav's docs give no lifetime for a link, so this is an assumption.
    link_valid_minutes: int = Field(default=15, ge=1)
    # Above this gap between prices, the airline's own price decides.
    price_conflict_percent: Decimal = Field(default=Decimal(10), ge=0)
    # Every search is compared with its seller's price, and a gap above this is logged.
    price_gap_log_percent: Decimal = Field(default=Decimal(5), ge=0)
    price_accuracy_db: Path = LOCAL_DIR / "price-accuracy.sqlite3"
    # An agent cheaper than the airline by this much is offered as an option.
    agent_cheaper_percent: Decimal = Field(default=Decimal(5), ge=0)
    # Price age: fresh below the first, old above the second.
    price_fresh_hours: int = Field(default=3, ge=1)
    price_stale_hours: int = Field(default=24, ge=1)
    # US-13: a general daily allowance per person for meals and small expenses.
    # It is not from a source, so the page always marks it Unconfirmed.
    meals_per_day_sar: Decimal = Field(default=Decimal(150), ge=0, decimal_places=2)

    # Free city photos from Wikimedia, kept locally with their licence.
    place_images_enabled: bool = True
    place_images_db: Path = LOCAL_DIR / "place-images.sqlite3"
    place_images_ttl_days: int = Field(default=30, ge=1)
    # Only these sites may name or price a stay. Everything else gives ideas only.
    # An entry can include a path, as in google.com/travel.
    booking_domains: list[str] = Field(
        default_factory=lambda: list(DEFAULT_BOOKING_DOMAINS)
    )
