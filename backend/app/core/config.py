from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    login_limit_db: Path = BACKEND_DIR / ".local" / "login-limits.sqlite3"

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
