import json
from collections.abc import Callable

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.supabase import get_supabase_http

ALICE = "11111111-1111-4111-8111-111111111111"
BOB = "22222222-2222-4222-8222-222222222222"
PROFILE = {"id": ALICE, "display_name": "Alice", "created_at": "2026-10-14T00:00:00Z"}


@pytest.fixture
def account_client():
    def build(handler: Callable[[httpx.Request], httpx.Response]) -> TestClient:
        app = create_app(Settings(_env_file=None, app_env="test"))

        async def fake_http():
            async with httpx.AsyncClient(
                base_url="https://supabase.example/",
                headers={"apikey": "sb_publishable_test"},
                transport=httpx.MockTransport(handler),
            ) as upstream:
                yield upstream

        app.dependency_overrides[get_supabase_http] = fake_http
        return TestClient(app)

    return build


@pytest.mark.parametrize("path", ["/api/me", "/api/profile"])
@pytest.mark.parametrize("header", [None, "Basic abc", "Bearer "])
def test_missing_credentials_are_rejected(client, path, header):
    response = client.get(path, headers={"Authorization": header} if header else {})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_unconfigured_auth_does_not_break_health(client):
    assert client.get("/health").status_code == 200
    assert (
        client.get("/api/me", headers={"Authorization": "Bearer token"}).status_code
        == 503
    )


@pytest.mark.parametrize("status", [401, 403])
def test_rejected_or_expired_tokens_cannot_access_profiles(account_client, status):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, json={"msg": "sensitive upstream details"})

    response = account_client(handler).get(
        "/api/profile", headers={"Authorization": "Bearer forged-or-expired-token"}
    )
    assert response.status_code == 401
    assert len(requests) == 1
    assert requests[0].url.path == "/auth/v1/user"
    assert "sensitive" not in response.text


def test_me_uses_authoritatively_verified_identity(account_client):
    def handler(request):
        assert request.url.path == "/auth/v1/user"
        assert request.headers["Authorization"] == "Bearer alice-token"
        assert request.headers["apikey"] == "sb_publishable_test"
        return httpx.Response(200, json={"id": ALICE, "email": "alice@example.test"})

    response = account_client(handler).get(
        "/api/me", headers={"Authorization": "Bearer alice-token"}
    )
    assert response.status_code == 200
    assert response.json() == {"id": ALICE, "email": "alice@example.test"}
    assert "token" not in response.text


@pytest.mark.parametrize("payload", [None, {}, {"id": "bad", "email": "a@b.c"}])
def test_malformed_auth_response_is_not_accepted(account_client, payload):
    response = account_client(lambda _: httpx.Response(200, json=payload)).get(
        "/api/me", headers={"Authorization": "Bearer token"}
    )
    assert response.status_code == 503


def test_anonymous_supabase_account_is_not_a_registered_account(account_client):
    response = account_client(
        lambda _: httpx.Response(
            200,
            json={
                "id": ALICE,
                "email": "alice@example.test",
                "is_anonymous": True,
            },
        )
    ).get("/api/me", headers={"Authorization": "Bearer token"})
    assert response.status_code == 401


def test_auth_network_failure_is_recoverable(account_client):
    def handler(request):
        raise httpx.ConnectError("private connection details", request=request)

    response = account_client(handler).get(
        "/api/me", headers={"Authorization": "Bearer token"}
    )
    assert response.status_code == 503
    assert "private" not in response.text


@pytest.mark.parametrize("status", [400, 429, 500])
def test_upstream_failures_do_not_impersonate_a_user(account_client, status):
    response = account_client(lambda _: httpx.Response(status)).get(
        "/api/me", headers={"Authorization": "Bearer token"}
    )
    assert response.status_code == 503


def test_requests_preserve_each_users_identity_and_rls_context(account_client):
    def handler(request):
        owner = ALICE if request.headers["Authorization"] == "Bearer alice" else BOB
        if request.url.path == "/auth/v1/user":
            return httpx.Response(200, json={"id": owner, "email": "user@example.test"})
        assert request.headers["apikey"] == "sb_publishable_test"
        assert request.url.params["id"] == f"eq.{owner}"
        assert request.url.params["select"] == "id,display_name,created_at"
        return httpx.Response(200, json=[{**PROFILE, "id": owner}])

    client = account_client(handler)
    for token, owner in [("alice", ALICE), ("bob", BOB), ("alice", ALICE)]:
        response = client.get(
            "/api/profile", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        assert response.json()["id"] == owner


def test_save_derives_owner_from_verified_token(account_client):
    def handler(request):
        if request.url.path == "/auth/v1/user":
            return httpx.Response(
                200, json={"id": ALICE, "email": "alice@example.test"}
            )
        assert request.method == "POST"
        assert json.loads(request.content) == {"id": ALICE, "display_name": "Alice"}
        assert request.headers["Authorization"] == "Bearer alice"
        assert (
            request.headers["Prefer"]
            == "resolution=merge-duplicates,return=representation"
        )
        assert request.url.params["on_conflict"] == "id"
        return httpx.Response(201, json=[PROFILE])

    response = account_client(handler).put(
        "/api/profile",
        headers={"Authorization": "Bearer alice"},
        json={"display_name": "  Alice  "},
    )
    assert response.status_code == 200
    assert response.json() == PROFILE


@pytest.mark.parametrize(
    "body",
    [
        {"display_name": "Alice", "id": BOB},
        {"display_name": " "},
        {"display_name": "x" * 81},
        {},
    ],
)
def test_invalid_or_forged_profile_input_never_reaches_database(account_client, body):
    def handler(request):
        assert request.url.path == "/auth/v1/user"
        return httpx.Response(200, json={"id": ALICE, "email": "alice@example.test"})

    response = account_client(handler).put(
        "/api/profile",
        headers={"Authorization": "Bearer alice"},
        json=body,
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("status", "rows", "expected"),
    [
        (200, [], 200),
        (200, [{**PROFILE, "id": BOB}], 503),
        (200, {"unexpected": "object"}, 503),
        (403, {}, 403),
        (404, {}, 503),
        (401, {}, 401),
    ],
)
def test_profile_results_and_storage_failures(account_client, status, rows, expected):
    def handler(request):
        if request.url.path == "/auth/v1/user":
            return httpx.Response(
                200, json={"id": ALICE, "email": "alice@example.test"}
            )
        return httpx.Response(status, json=rows)

    response = account_client(handler).get(
        "/api/profile", headers={"Authorization": "Bearer alice"}
    )
    assert response.status_code == expected
    if rows == []:
        assert response.json() is None
