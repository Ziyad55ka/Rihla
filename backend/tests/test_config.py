from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_optional_supabase_values_can_be_missing() -> None:
    settings = Settings(_env_file=None)

    assert settings.supabase_url is None
    assert settings.supabase_publishable_key is None
    assert settings.app_env == "development"


def test_settings_load_a_dotenv_independently_of_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        'APP_ENV=test\nCORS_ORIGINS=["http://localhost:4200"]\n'
        "SUPABASE_URL=\nSUPABASE_PUBLISHABLE_KEY=\n",
        encoding="utf-8",
    )
    nested_directory = tmp_path / "nested"
    nested_directory.mkdir()
    monkeypatch.chdir(nested_directory)

    settings = Settings(_env_file=env_file)

    assert settings.app_env == "test"
    assert settings.cors_origins == ["http://localhost:4200"]
    assert settings.supabase_url is None
    assert settings.supabase_publishable_key is None


def test_environment_variables_override_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text('CORS_ORIGINS=["http://localhost:4200"]\n', encoding="utf-8")
    monkeypatch.setenv("CORS_ORIGINS", '["https://rihla.example"]')

    settings = Settings(_env_file=env_file)

    assert settings.cors_origins == ["https://rihla.example"]


@pytest.mark.parametrize("origin", ["*", "https://*.example", "http://localhost:5173/"])
def test_settings_reject_wildcards_and_paths_in_origins(origin: str) -> None:
    with pytest.raises(ValidationError, match="explicit http"):
        Settings(_env_file=None, cors_origins=[origin])
