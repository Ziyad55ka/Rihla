import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    # Tests must never count towards the real Ignav usage file.
    monkeypatch.setenv("FLIGHT_USAGE_DB", str(tmp_path / "flight-usage.sqlite3"))
    # Nor reach Wikimedia or Trip.com.
    monkeypatch.setenv("PLACE_IMAGES_ENABLED", "false")
    monkeypatch.setenv("TRIPCOM_ENABLED", "false")
    for variable in (
        "APP_ENV",
        "CORS_ORIGINS",
        "SUPABASE_URL",
        "SUPABASE_PUBLISHABLE_KEY",
        "SUPABASE_SECRET_KEY",
        "LOGIN_LIMIT_DB",
        "PROPOSALS_HASH_KEY",
        "PROPOSALS_DEMO_MODE",
        "PROPOSALS_DEMO_FILE",
        "IGNAV_API_KEY",
        "FLIGHT_PRICE_PROVIDER",
        "MIN_BUDGET_SAR_PER_DAY",
        "MAX_GEMINI_CALLS_PER_GENERATION",
        "GENERATION_STORE_DB",
        "SAVED_PROPOSALS_TTL_HOURS",
        "GEMINI_API_KEY",
        "GEMINI_MODEL",
        "GEMINI_RETRY_DELAY_SECONDS",
        "TAVILY_API_KEY",
        "TAVILY_SEARCH_DEPTH",
        "TAVILY_MAX_RESULTS",
        "SEARCH_CACHE_DB",
        "SEARCH_CACHE_TTL_HOURS",
    ):
        monkeypatch.delenv(variable, raising=False)


@pytest.fixture
def client() -> TestClient:
    settings = Settings(_env_file=None, app_env="test")
    return TestClient(create_app(settings))
