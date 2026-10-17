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
    ):
        monkeypatch.delenv(variable, raising=False)


@pytest.fixture
def client() -> TestClient:
    settings = Settings(_env_file=None, app_env="test")
    return TestClient(create_app(settings))
