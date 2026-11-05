import json
from concurrent.futures import ThreadPoolExecutor

import httpx2 as httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.login_limits import WINDOW, LoginLimits
from app.services.supabase import get_supabase_http


@pytest.fixture
def limits(tmp_path):
    now = [1000.0]
    return LoginLimits(tmp_path / "limits.sqlite3", clock=lambda: now[0]), now


def test_fifth_failure_blocks_even_correct_credentials_until_cooldown(limits):
    guard, now = limits
    for index in range(5):
        lease = guard.reserve("User@Example.test")
        assert guard.complete(lease, "invalid") == (WINDOW if index == 4 else 0)
    with pytest.raises(HTTPException) as caught:
        guard.reserve("user@example.test")
    assert caught.value.status_code == 429
    assert caught.value.headers["Retry-After"] == str(WINDOW)
    now[0] += WINDOW
    assert guard.complete(guard.reserve("user@example.test"), "success") == 0


def test_outages_and_success_do_not_count_or_erase_rolling_failures(limits):
    guard, _ = limits
    for _ in range(4):
        guard.complete(guard.reserve("user@example.test"), "invalid")
    guard.complete(guard.reserve("user@example.test"), "other")
    guard.complete(guard.reserve("user@example.test"), "success")
    assert guard.complete(guard.reserve("user@example.test"), "invalid") == WINDOW


def test_failures_use_a_rolling_fifteen_minute_window(limits):
    guard, now = limits
    for _ in range(4):
        guard.complete(guard.reserve("user@example.test"), "invalid")
    now[0] += WINDOW
    assert guard.complete(guard.reserve("user@example.test"), "invalid") == 0


def test_accounts_are_independent_and_limits_survive_new_instances(limits):
    guard, now = limits
    for _ in range(5):
        guard.complete(guard.reserve("user@example.test"), "invalid")
    reopened = LoginLimits(guard.path, clock=lambda: now[0])
    with pytest.raises(HTTPException):
        reopened.reserve(" USER@example.test ")
    assert reopened.complete(reopened.reserve("other@example.test"), "success") == 0
    assert b"user@example.test" not in guard.path.read_bytes()


def test_concurrent_requests_cannot_reserve_the_same_account(limits):
    guard, _ = limits

    def attempt(_):
        try:
            return guard.reserve("user@example.test")
        except HTTPException as error:
            assert error.status_code == 429
            return None

    with ThreadPoolExecutor(max_workers=6) as workers:
        results = list(workers.map(attempt, range(6)))
    assert sum(result is not None for result in results) == 1


def test_expired_attempt_is_recoverable_and_cannot_overwrite_new_attempt(limits):
    guard, now = limits
    old = guard.reserve("user@example.test")
    now[0] += 61
    current = guard.reserve("user@example.test")
    with pytest.raises(HTTPException) as caught:
        guard.complete(old, "success")
    assert caught.value.status_code == 503
    guard.complete(current, "success")


def test_login_guard_fails_closed_if_storage_is_unavailable(tmp_path):
    directory = tmp_path / "not-a-file"
    directory.mkdir()
    with pytest.raises(HTTPException) as caught:
        LoginLimits(directory).reserve("user@example.test")
    assert caught.value.status_code == 503


@pytest.fixture
def login_client(tmp_path):
    calls = []

    def build(handler):
        app = create_app(
            Settings(
                _env_file=None, app_env="test", login_limit_db=tmp_path / "api.sqlite3"
            )
        )

        async def fake_http():
            def upstream(request):
                assert request.url.path == "/auth/v1/token"
                assert request.url.params["grant_type"] == "password"
                assert request.headers["apikey"] == "sb_publishable_test"
                assert "authorization" not in request.headers
                calls.append(json.loads(request.content))
                return handler(request)

            async with httpx.AsyncClient(
                base_url="https://supabase.example/",
                headers={"apikey": "sb_publishable_test"},
                transport=httpx.MockTransport(upstream),
            ) as client:
                yield client

        app.dependency_overrides[get_supabase_http] = fake_http
        return TestClient(app), calls

    return build


def test_login_returns_only_supabase_session_and_never_caches_it(login_client):
    client, calls = login_client(
        lambda _: httpx.Response(
            200,
            json={
                "access_token": "access",
                "refresh_token": "refresh",
                "sensitive_extra": "not returned",
            },
        )
    )
    response = client.post(
        "/api/auth/login",
        json={"email": "USER@example.test", "password": "private-password"},
    )
    assert response.status_code == 200
    assert response.json() == {"access_token": "access", "refresh_token": "refresh"}
    assert response.headers["cache-control"] == "no-store"
    assert calls == [{"email": "user@example.test", "password": "private-password"}]


def test_lockout_is_server_enforced_and_does_not_send_a_sixth_request(login_client):
    client, calls = login_client(
        lambda _: httpx.Response(
            400,
            json={"code": "invalid_credentials", "message": "private upstream detail"},
        )
    )
    body = {"email": "user@example.test", "password": "wrong"}
    for _ in range(4):
        assert client.post("/api/auth/login", json=body).status_code == 401
    fifth = client.post("/api/auth/login", json=body)
    assert fifth.status_code == 429
    assert fifth.json()["detail"]["code"] == "login_locked"
    sixth = client.post("/api/auth/login", json={**body, "password": "correct"})
    assert sixth.status_code == 429
    assert "Retry-After" in sixth.headers
    assert len(calls) == 5
    assert "private upstream detail" not in sixth.text
    assert "wrong" not in sixth.text


@pytest.mark.parametrize(
    ("status", "payload", "expected"),
    [
        (403, {"code": "email_not_confirmed"}, 403),
        (429, {"code": "over_request_rate_limit"}, 429),
        (500, {"message": "private details"}, 503),
        (500, {"code": "invalid_credentials"}, 503),
        (200, {"access_token": "missing refresh"}, 503),
    ],
)
def test_login_provider_failures_are_safe_and_release_the_reservation(
    login_client, status, payload, expected
):
    client, calls = login_client(lambda _: httpx.Response(status, json=payload))
    for _ in range(6):
        response = client.post(
            "/api/auth/login",
            json={"email": "user@example.test", "password": "password"},
        )
        assert response.status_code == expected
        assert "private details" not in response.text
    assert len(calls) == 6


def test_login_network_failure_releases_the_reservation_without_counting_a_bad_password(
    login_client,
):
    def unavailable(request):
        raise httpx.ConnectError("private network detail", request=request)

    client, calls = login_client(unavailable)
    for _ in range(6):
        response = client.post(
            "/api/auth/login",
            json={"email": "user@example.test", "password": "password"},
        )
        assert response.status_code == 503
        assert "private network detail" not in response.text
    assert len(calls) == 6


@pytest.mark.parametrize(
    "body",
    [
        {"email": "bad", "password": "password"},
        {"email": "user@example.test", "password": ""},
        {"email": "user@example.test", "password": "password", "user_id": "forged"},
    ],
)
def test_invalid_login_input_does_not_reach_supabase(login_client, body):
    client, calls = login_client(
        lambda _: pytest.fail("Invalid input reached Supabase")
    )
    assert client.post("/api/auth/login", json=body).status_code == 422
    assert calls == []


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"code": 400, "error_code": "invalid_credentials", "msg": "x"}, 401),
        (
            {
                "error": "invalid_grant",
                "error_description": "Invalid login credentials",
            },
            401,
        ),
        ({"code": 400, "error_code": "email_not_confirmed", "msg": "x"}, 403),
        ({"error": "invalid_grant", "error_description": "Email not confirmed"}, 403),
    ],
)
def test_current_and_older_supabase_error_shapes_are_understood(
    login_client, payload, expected
):
    client, _ = login_client(lambda _: httpx.Response(400, json=payload))
    response = client.post(
        "/api/auth/login", json={"email": "user@example.test", "password": "wrong"}
    )
    assert response.status_code == expected
