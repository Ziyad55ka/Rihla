from decimal import Decimal
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
)
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Read backend/.env consistently, with environment variables taking priority."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )
    # Optional for /health; required by authenticated account/profile endpoints.
    supabase_url: str | None = None
    supabase_publishable_key: str | None = None
    # Bypasses Row Level Security. Used only by services/generation_inputs.py.
    supabase_secret_key: str | None = Field(default=None, repr=False)
    login_limit_db: Path = BACKEND_DIR / ".local" / "login-limits.sqlite3"
    # Keys the stored inputs hash, so budgets cannot be guessed from it.
    proposals_hash_key: str | None = Field(default=None, repr=False)
    # Serve saved proposals instead of calling Gemini and Tavily.
    proposals_demo_mode: bool = False
    proposals_demo_file: Path = BACKEND_DIR / "app" / "data" / "demo_proposals.json"
    # Optional for the API; required only by trip research.
    # ignav: live fares, falling back to web search. tavily: web search only.
    flight_price_provider: Literal["ignav", "tavily"] = "ignav"
    ignav_api_key: str | None = None
    # Below this per trip day, generation stops before any outside request.
    min_budget_sar_per_day: Decimal = Field(default=Decimal(250), gt=0)
    generation_store_db: Path = BACKEND_DIR / ".local" / "generations.sqlite3"
    saved_proposals_ttl_hours: int = Field(default=24, ge=1)
    # Generation stops here and returns the proposals that already passed.
    max_gemini_calls_per_generation: int = Field(default=7, ge=1)
    # An Ignav amount covers the whole party: tested with 1 and 2 adults, 1 Nov 2026.
    ignav_price_scope: Literal["per_person", "total"] = "total"
    # A split trip must save this much, and may take only this much longer.
    split_min_saving_percent: Decimal = Field(default=Decimal(15), ge=0, lt=100)
    split_max_extra_duration_percent: Decimal = Field(default=Decimal(30), ge=0)
    # The light flight update: cache and limits, all to protect the free requests.
    flight_cache_minutes: int = Field(default=15, ge=0)
    member_flight_actions_per_hour: int = Field(default=5, ge=0)
    trip_ignav_requests_per_day: int = Field(default=30, ge=0)
    daily_ignav_requests: int = Field(default=200, ge=0)
    refresh_cooldown_minutes: int = Field(default=5, ge=0)
    flight_usage_db: Path = BACKEND_DIR / ".local" / "flight-usage.sqlite3"
    # Price age: fresh below the first, old above the second.
    price_fresh_hours: int = Field(default=3, ge=1)
    price_stale_hours: int = Field(default=24, ge=1)
    # Only these sites may name or price a stay. Everything else gives ideas only.
    # An entry can include a path, as in google.com/travel.
    booking_domains: list[str] = Field(
        default_factory=lambda: list(DEFAULT_BOOKING_DOMAINS)
    )
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3-flash-preview"
    gemini_retry_delay_seconds: float = Field(default=20, ge=0)
    tavily_api_key: str | None = None
    tavily_search_depth: Literal["basic", "advanced"] = "basic"
    tavily_max_results: int = Field(default=5, ge=1, le=20)
    search_cache_db: Path = BACKEND_DIR / ".local" / "search-cache.sqlite3"
    search_cache_ttl_hours: int = Field(default=24, ge=1)

    @field_validator("supabase_url")
    @classmethod
    def validate_supabase_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if (
            not parsed.hostname
            or (parsed.scheme != "https" and not (local and parsed.scheme == "http"))
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("Use an https Supabase project URL (http for localhost).")
        return value

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, origins: list[str]) -> list[str]:
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username
                or parsed.password
                or "*" in origin
            ):
                raise ValueError(
                    "Each CORS origin must be an explicit http(s) origin "
                    "without a path or wildcard, such as http://localhost:5173."
                )
        return origins
