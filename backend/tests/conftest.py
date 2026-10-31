import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in (
        "APP_ENV",
        "CORS_ORIGINS",
        "SUPABASE_URL",
        "SUPABASE_PUBLISHABLE_KEY",
        "LOGIN_LIMIT_DB",
        "FLIGHT_VISIBILITY",
        "PROPOSALS_DEMO_MODE",
        "PROPOSALS_DEMO_FILE",
        "IGNAV_API_KEY",
        "FLIGHT_PRICE_PROVIDER",
        "MIN_BUDGET_SAR_PER_DAY",
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
