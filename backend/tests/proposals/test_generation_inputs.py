"""Secret-key tests with a fake transport. Nothing here reaches Supabase."""

import asyncio
import json
import re
from pathlib import Path
from uuid import UUID

import httpx2 as httpx
import pytest

from app.core.config import Settings
from app.services.generation_inputs import (
    GenerationInputsError,
    fetch_generation_inputs,
    save_generated_proposals,
)
from app.services.generation_precheck import COUNTRY_WORDS, STOP_WORDS

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent
TRIP = UUID("00000000-0000-4000-8000-0000000000aa")
ADMIN = UUID("11111111-1111-4111-8111-111111111111")
MIGRATION = ROOT / "supabase/migrations/20261102000100_ai_proposals.sql"
PAYLOAD = {
    "trip_id": str(TRIP),
    "shared_start": "2026-12-13",
    "shared_end": "2026-12-17",
    "members": [
        {
            "label": "Member 1",
            "departure_city": "Riyadh",
            "max_budget_sar": "4000.00",
            "destinations": {"value": "", "importance": "Flexible"},
            "interests": {"value": "", "importance": "Flexible"},
            "flights": {"value": "", "importance": "Flexible"},
            "accommodation": {"value": "", "importance": "Flexible"},
        }
    ],
}


def settings() -> Settings:
    return Settings(
        _env_file=None,
        supabase_url="https://example.supabase.co",
        supabase_secret_key="test-secret",
    )


def fetch(response: httpx.Response, config: Settings | None = None, calls=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        return response

    return asyncio.run(
        fetch_generation_inputs(
            TRIP, ADMIN, config or settings(), httpx.MockTransport(handler)
        )
    )


def test_fetch_sends_the_secret_key_and_verified_admin() -> None:
    calls: list[httpx.Request] = []

    result = fetch(httpx.Response(200, json=PAYLOAD), calls=calls)

    assert result.members[0].label == "Member 1"
    assert calls[0].url.path == "/rest/v1/rpc/rihla_trip_generation_inputs"
    assert calls[0].headers["apikey"] == "test-secret"
    assert "authorization" not in calls[0].headers
    assert json.loads(calls[0].content) == {
        "p_trip_id": str(TRIP),
        "p_admin_id": str(ADMIN),
    }


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (httpx.Response(400, json={"message": "generation_not_ready"}), "not_ready"),
        (httpx.Response(403, json={"message": "trip_access_denied"}), "access_denied"),
        (httpx.Response(500, text="test-secret leaked"), "unavailable"),
        (httpx.Response(200, json={"members": []}), "invalid_response"),
    ],
)
def test_failures_are_general_and_hide_the_key(
    response: httpx.Response, code: str
) -> None:
    with pytest.raises(GenerationInputsError) as caught:
        fetch(response)

    assert caught.value.code == code
    assert "test-secret" not in str(caught.value)


def test_missing_key_stops_before_any_request() -> None:
    calls: list[httpx.Request] = []
    config = Settings(_env_file=None, supabase_url="https://example.supabase.co")

    with pytest.raises(GenerationInputsError) as caught:
        fetch(httpx.Response(200, json=PAYLOAD), config, calls)

    assert caught.value.code == "not_configured"
    assert calls == []


def test_secret_key_is_used_in_one_place_only() -> None:
    users = {
        path.relative_to(BACKEND).as_posix()
        for path in (BACKEND / "app").rglob("*.py")
        if re.search(
            r"supabase_secret_key|SUPABASE_SECRET_KEY", path.read_text(encoding="utf-8")
        )
    }

    assert users == {
        "app/core/proposal_settings.py",
        "app/services/generation_inputs.py",
    }


def test_secret_key_never_reaches_the_frontend_or_its_examples() -> None:
    for path in (ROOT / "frontend").glob("*.example"):
        assert "SECRET" not in path.read_text(encoding="utf-8")
    source = ROOT / "frontend/src"
    for path in source.rglob("*.ts*"):
        assert "SUPABASE_SECRET" not in path.read_text(encoding="utf-8")


def test_settings_repr_hides_the_secret_key() -> None:
    assert "test-secret" not in repr(settings())


def test_example_env_has_no_value_for_the_secret_key() -> None:
    example = (BACKEND / ".env.example").read_text(encoding="utf-8")

    assert re.search(r"^SUPABASE_SECRET_KEY=$", example, re.MULTILINE)


def test_sql_rules_stay_in_step_with_the_python_rules() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    default_floor = Settings(_env_file=None).min_budget_sar_per_day

    for word, country in COUNTRY_WORDS.items():
        assert f"('{word}', '{country}')" in sql
    for word in STOP_WORDS:
        assert f"'{word}'" in sql
    assert f"v_lowest < {default_floor} *" in sql


def test_legacy_service_role_key_is_also_sent_as_a_bearer_token() -> None:
    calls: list[httpx.Request] = []
    config = settings().model_copy(update={"supabase_secret_key": "eyJlegacy"})

    fetch(httpx.Response(200, json=PAYLOAD), config, calls)

    assert calls[0].headers["apikey"] == "eyJlegacy"
    assert calls[0].headers["authorization"] == "Bearer eyJlegacy"


def test_saving_uses_the_secret_key_and_verified_admin() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"saved": True})

    asyncio.run(
        save_generated_proposals(
            str(TRIP),
            ADMIN,
            2,
            "hash",
            True,
            [],
            settings(),
            httpx.MockTransport(handler),
        )
    )

    assert calls[0].url.path == "/rest/v1/rpc/rihla_save_proposals"
    assert calls[0].headers["apikey"] == "test-secret"
    sent = json.loads(calls[0].content)
    assert sent["p_admin_id"] == str(ADMIN)
    assert sent["p_version"] == 2


def test_saving_failure_is_general_and_hides_the_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="test-secret leaked")

    with pytest.raises(GenerationInputsError) as caught:
        asyncio.run(
            save_generated_proposals(
                str(TRIP),
                ADMIN,
                1,
                "h",
                True,
                [],
                settings(),
                httpx.MockTransport(handler),
            )
        )

    assert caught.value.code == "unavailable"
    assert "test-secret" not in str(caught.value)
