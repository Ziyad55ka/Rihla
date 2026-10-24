import json

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.supabase import get_supabase_http

USER = "11111111-1111-4111-8111-111111111111"
TRIP_ID = "44444444-4444-4444-8444-444444444444"
TOKEN = "ab" * 32
CODE = "984143"
TRIP = {
    "id": TRIP_ID,
    "title": "Our next trip",
    "description": "Together",
    "created_at": "2026-10-16T12:00:00Z",
    "role": "administrator",
    "member_count": 1,
    "members": [
        {
            "user_id": USER,
            "display_name": "Alice",
            "role": "administrator",
            "joined_at": "2026-10-16T12:00:00Z",
        }
    ],
}


@pytest.fixture
def trip_client(tmp_path):
    def build(handler):
        app = create_app(
            Settings(
                _env_file=None,
                app_env="test",
                login_limit_db=tmp_path / "trip-limits.sqlite3",
            )
        )

        async def fake_http():
            def upstream(request):
                assert request.headers["Authorization"] == "Bearer current-user"
                assert request.headers["apikey"] == "sb_publishable_test"
                if request.url.path == "/auth/v1/user":
                    return httpx.Response(
                        200, json={"id": USER, "email": "test@example.test"}
                    )
                return handler(request)

            async with httpx.AsyncClient(
                base_url="https://supabase.example/",
                headers={"apikey": "sb_publishable_test"},
                transport=httpx.MockTransport(upstream),
            ) as client:
                yield client

        app.dependency_overrides[get_supabase_http] = fake_http
        return TestClient(app)

    return build


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/trips"),
        ("POST", "/api/trips"),
        ("POST", "/api/trips/join"),
        ("GET", f"/api/trips/{TRIP_ID}"),
        ("GET", f"/api/trips/{TRIP_ID}/invitation"),
        ("POST", f"/api/trips/{TRIP_ID}/invitation"),
        ("DELETE", f"/api/trips/{TRIP_ID}/invitation"),
    ],
)
def test_all_trip_routes_require_authentication(client, method, path):
    assert client.request(method, path).status_code == 401


@pytest.mark.parametrize(
    ("method", "path", "body", "rpc", "args", "result", "status"),
    [
        ("GET", "/api/trips", None, "rihla_list_trips", {}, [TRIP], 200),
        (
            "POST",
            "/api/trips",
            {"title": "  Our next trip  ", "description": "Together"},
            "rihla_create_trip",
            {"p_title": "Our next trip", "p_description": "Together"},
            TRIP,
            201,
        ),
        (
            "GET",
            f"/api/trips/{TRIP_ID}",
            None,
            "rihla_get_trip",
            {"p_trip_id": TRIP_ID},
            TRIP,
            200,
        ),
        (
            "POST",
            "/api/trips/join",
            {"token": TOKEN},
            "rihla_join_trip",
            {"p_token": TOKEN},
            {"trip": TRIP, "already_member": True},
            200,
        ),
        (
            "GET",
            f"/api/trips/{TRIP_ID}/invitation",
            None,
            "rihla_get_invitation",
            {"p_trip_id": TRIP_ID},
            {"exists": False, "expires_at": None, "revoked": False},
            200,
        ),
        (
            "POST",
            f"/api/trips/{TRIP_ID}/invitation",
            None,
            "rihla_issue_invitation",
            {"p_trip_id": TRIP_ID},
            {"token": TOKEN, "code": CODE, "expires_at": "2026-10-23T12:00:00Z"},
            201,
        ),
        (
            "DELETE",
            f"/api/trips/{TRIP_ID}/invitation",
            None,
            "rihla_revoke_invitation",
            {"p_trip_id": TRIP_ID},
            {"exists": True, "expires_at": "2026-10-23T12:00:00Z", "revoked": True},
            200,
        ),
    ],
)
def test_trip_routes_preserve_user_context_and_exact_rpc_arguments(
    trip_client,
    method,
    path,
    body,
    rpc,
    args,
    result,
    status,
):
    def handler(request):
        assert request.url.path == f"/rest/v1/rpc/{rpc}"
        assert request.method == "POST"
        assert json.loads(request.content) == args
        return httpx.Response(200, json=result)

    response = trip_client(handler).request(
        method,
        path,
        json=body,
        headers={"Authorization": "Bearer current-user"},
    )
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "body",
    [
        {"title": "x"},
        {"title": "  "},
        {"title": "x" * 101},
        {"title": "Valid", "description": "x" * 501},
        {"title": "Valid", "created_by": USER},
        {"title": "Valid", "role": "administrator"},
    ],
)
def test_trip_input_cannot_forge_identity_or_bypass_validation(trip_client, body):
    def never_called(_):
        pytest.fail("Invalid input reached database")

    response = trip_client(never_called).post(
        "/api/trips",
        json=body,
        headers={"Authorization": "Bearer current-user"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("body", [{"token": "bad"}, {"token": TOKEN, "user_id": USER}])
def test_invalid_join_input_is_rejected(trip_client, body):
    response = trip_client(lambda _: pytest.fail("Invalid join reached database")).post(
        "/api/trips/join",
        json=body,
        headers={"Authorization": "Bearer current-user"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("upstream_status", "code", "expected"),
    [
        (400, "P0001", 503),
        (403, "42501", 403),
        (400, "23514", 422),
        (404, "PGRST202", 503),
        (401, "invalid_jwt", 401),
        (500, "XX000", 503),
    ],
)
def test_database_errors_are_safe_and_actionable(
    trip_client, upstream_status, code, expected
):
    response = trip_client(
        lambda _: httpx.Response(
            upstream_status,
            json={
                "code": code,
                "message": "sensitive database details with invitation token",
            },
        )
    ).get("/api/trips", headers={"Authorization": "Bearer current-user"})
    assert response.status_code == expected
    assert "sensitive" not in response.text


def test_invalid_database_shape_cannot_be_reported_as_success(trip_client):
    response = trip_client(
        lambda _: httpx.Response(200, json={"unexpected": True})
    ).get(
        "/api/trips",
        headers={"Authorization": "Bearer current-user"},
    )
    assert response.status_code == 503


def test_join_reports_invalid_expired_or_revoked_invitation(trip_client):
    response = trip_client(lambda _: httpx.Response(400, json={"code": "P0001"})).post(
        "/api/trips/join",
        json={"token": TOKEN},
        headers={"Authorization": "Bearer current-user"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == (
        "This invitation is invalid, expired or revoked."
    )


def test_six_digit_code_joins_through_the_same_guarded_rpc(trip_client):
    def handler(request):
        assert request.url.path == "/rest/v1/rpc/rihla_join_trip"
        assert json.loads(request.content) == {"p_token": CODE}
        return httpx.Response(200, json={"trip": TRIP, "already_member": False})

    response = trip_client(handler).post(
        "/api/trips/join",
        json={"token": CODE},
        headers={"Authorization": "Bearer current-user"},
    )
    assert response.status_code == 200
    assert response.json()["already_member"] is False


def test_fifth_invalid_short_code_blocks_more_guesses_for_that_user(trip_client):
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(400, json={"code": "P0001"})

    client = trip_client(handler)
    headers = {"Authorization": "Bearer current-user"}
    for _ in range(4):
        assert (
            client.post(
                "/api/trips/join", json={"token": CODE}, headers=headers
            ).status_code
            == 404
        )
    fifth = client.post("/api/trips/join", json={"token": CODE}, headers=headers)
    assert fifth.status_code == 429
    assert fifth.json()["detail"]["code"] == "invitation_join_locked"
    sixth = client.post("/api/trips/join", json={"token": "123456"}, headers=headers)
    assert sixth.status_code == 429
    assert len(calls) == 5


def test_trip_output_filters_unexpected_private_fields(trip_client):
    response = trip_client(
        lambda _: httpx.Response(
            200,
            json={
                **TRIP,
                "budget": 3000,
                "missing_fields": ["departure_city"],
            },
        )
    ).get(f"/api/trips/{TRIP_ID}", headers={"Authorization": "Bearer current-user"})
    assert response.status_code == 200
    assert "budget" not in response.json()
    assert "missing_fields" not in response.json()


PREFERENCES = {
    "departure_city": "Riyadh",
    "max_budget_sar": "4500.50",
    "available_start": "2026-11-10",
    "available_end": "2026-11-15",
    "destinations": {"value": "Japan", "importance": "Flexible"},
    "interests": {"value": "", "importance": "Flexible"},
    "flights": {"value": "Direct flights", "importance": "Essential"},
    "accommodation": {"value": "", "importance": "Flexible"},
}


PLANNING = {
    "all_members_ready": True,
    "own_readiness": {
        "status": "Ready",
        "missing_fields": [],
        "has_saved_preferences": True,
    },
    "member_readiness": [{"user_id": USER, "status": "Ready"}],
    "member_dates": [
        {
            "user_id": USER,
            "available_start": "2026-11-10",
            "available_end": "2026-11-15",
        }
    ],
    "shared_dates": {
        "status": "available",
        "start": "2026-11-10",
        "end": "2026-11-15",
        "duration_days": 6,
    },
}


def test_planning_status_requires_authentication(client):
    assert client.get(f"/api/trips/{TRIP_ID}/planning").status_code == 401


def test_planning_route_preserves_identity_and_does_not_accept_a_target_user(
    trip_client,
):
    def handler(request):
        assert request.url.path == "/rest/v1/rpc/rihla_get_planning_status"
        assert json.loads(request.content) == {"p_trip_id": TRIP_ID}
        return httpx.Response(200, json=PLANNING)

    response = trip_client(handler).get(
        f"/api/trips/{TRIP_ID}/planning",
        headers={"Authorization": "Bearer current-user"},
    )
    assert response.status_code == 200
    assert response.json() == PLANNING
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "patch",
    [
        {
            "member_dates": [
                {
                    "user_id": USER,
                    "available_start": "2026-11-10",
                    "available_end": "2026-11-15",
                    "max_budget_sar": "4500.50",
                }
            ]
        },
        {
            "member_readiness": [
                {
                    "user_id": USER,
                    "status": "Incomplete",
                    "missing_fields": ["max_budget_sar"],
                }
            ]
        },
        {
            "shared_dates": {
                "status": "conflict",
                "start": "2026-11-10",
                "end": None,
                "duration_days": None,
            }
        },
        {
            "shared_dates": {
                "status": "available",
                "start": "2026-11-10",
                "end": "2026-11-15",
                "duration_days": 5,
            }
        },
    ],
)
def test_invalid_or_overly_detailed_planning_response_fails_closed(trip_client, patch):
    response = trip_client(
        lambda _: httpx.Response(200, json={**PLANNING, **patch})
    ).get(
        f"/api/trips/{TRIP_ID}/planning",
        headers={"Authorization": "Bearer current-user"},
    )
    assert response.status_code == 503
    assert "missing_fields" not in response.json()


@pytest.mark.parametrize(
    ("status", "code", "expected"), [(403, "42501", 403), (404, "PGRST202", 503)]
)
def test_planning_denial_and_missing_migration_are_actionable(
    trip_client, status, code, expected
):
    response = trip_client(lambda _: httpx.Response(status, json={"code": code})).get(
        f"/api/trips/{TRIP_ID}/planning",
        headers={"Authorization": "Bearer current-user"},
    )
    assert response.status_code == expected


def test_date_check_requires_authentication(client):
    assert client.post(f"/api/trips/{TRIP_ID}/date-check").status_code == 401


@pytest.mark.parametrize("status", ["available", "conflict", "pending"])
def test_date_check_preserves_identity_and_returns_only_aggregate(trip_client, status):
    def handler(request):
        assert request.url.path == "/rest/v1/rpc/rihla_check_trip_dates"
        assert json.loads(request.content) == {
            "p_trip_id": TRIP_ID,
            "p_start": "2026-11-10",
            "p_end": "2026-11-10",
        }
        return httpx.Response(200, json={"status": status})

    response = trip_client(handler).post(
        f"/api/trips/{TRIP_ID}/date-check",
        json={"available_start": "2026-11-10", "available_end": "2026-11-10"},
        headers={"Authorization": "Bearer current-user"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": status}
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "patch",
    [
        {"user_id": USER},
        {"available_start": None},
        {"available_start": "2026-11-16"},
        {"available_start": "2026-02-30"},
        {"available_start": "2026-11-10T00:00:00Z"},
        {"available_start": "0000-01-01"},
        {"available_end": "10000-01-01"},
        {"available_start": 1794268800},
    ],
)
def test_date_check_rejects_invalid_or_targeted_input(trip_client, patch):
    response = trip_client(
        lambda _: pytest.fail("Invalid input reached database")
    ).post(
        f"/api/trips/{TRIP_ID}/date-check",
        json={
            "available_start": "2026-11-10",
            "available_end": "2026-11-15",
            **patch,
        },
        headers={"Authorization": "Bearer current-user"},
    )
    assert response.status_code == 422


def test_date_check_cannot_expose_private_intervals(trip_client):
    response = trip_client(
        lambda _: httpx.Response(
            200, json={"status": "conflict", "start": "2026-11-10"}
        )
    ).post(
        f"/api/trips/{TRIP_ID}/date-check",
        json={"available_start": "2026-11-10", "available_end": "2026-11-15"},
        headers={"Authorization": "Bearer current-user"},
    )
    assert response.status_code == 503
    assert "2026-11-10" not in response.text


@pytest.mark.parametrize(
    ("status", "code", "expected"),
    [(403, "42501", 403), (404, "PGRST202", 503), (400, "23514", 422)],
)
def test_date_check_denial_and_missing_migration_are_actionable(
    trip_client, status, code, expected
):
    response = trip_client(
        lambda _: httpx.Response(status, json={"code": code, "message": "private"})
    ).post(
        f"/api/trips/{TRIP_ID}/date-check",
        json={"available_start": "2026-11-10", "available_end": "2026-11-15"},
        headers={"Authorization": "Bearer current-user"},
    )
    assert response.status_code == expected
    assert "private" not in response.text
    if expected == 503:
        assert "planning overview" in response.json()["detail"]


@pytest.mark.parametrize("method", ["GET", "PUT"])
def test_preferences_require_authentication(client, method):
    assert (
        client.request(method, f"/api/trips/{TRIP_ID}/preferences").status_code == 401
    )


@pytest.mark.parametrize("method", ["GET", "PUT"])
def test_preferences_keep_user_token_without_accepting_target_user(trip_client, method):
    def handler(request):
        assert request.url.path == (
            "/rest/v1/rpc/rihla_get_preferences"
            if method == "GET"
            else "/rest/v1/rpc/rihla_save_preferences"
        )
        args = {"p_trip_id": TRIP_ID}
        if method == "PUT":
            args["p_preferences"] = PREFERENCES
        assert json.loads(request.content) == args
        return httpx.Response(
            200, json={**PREFERENCES, "currency": "SAR", "updated_at": None}
        )

    response = trip_client(handler).request(
        method,
        f"/api/trips/{TRIP_ID}/preferences",
        json=PREFERENCES if method == "PUT" else None,
        headers={"Authorization": "Bearer current-user"},
    )
    assert response.status_code == 200
    assert response.json()["max_budget_sar"] == "4500.50"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "patch",
    [
        {"user_id": USER},
        {"trip_id": TRIP_ID},
        {"currency": "USD"},
        {"max_budget_sar": "-1"},
        {"max_budget_sar": "0"},
        {"max_budget_sar": "1.001"},
        {"max_budget_sar": "10000000000"},
        {"max_budget_sar": "NaN"},
        {"max_budget_sar": None},
        {"departure_city": ""},
        {"departure_city": "   "},
        {"available_start": None},
        {"available_end": None},
        {"departure_city": "a" * 101},
        {"available_end": "2026-11-09"},
        {"available_start": "2026-02-30"},
        {"available_start": 1794268800},
        {"available_start": "2026-11-10T00:00:00Z"},
        {"destinations": {"value": "Japan", "importance": "Very flexible"}},
        {"flights": {"value": "x" * 501}},
        {"interests": {"value": "Food", "owner": USER}},
    ],
)
def test_invalid_preferences_never_reach_database(trip_client, patch):
    response = trip_client(lambda _: pytest.fail("Invalid input reached database")).put(
        f"/api/trips/{TRIP_ID}/preferences",
        json={**PREFERENCES, **patch},
        headers={"Authorization": "Bearer current-user"},
    )
    assert response.status_code == 422


def test_preferences_allow_complete_single_day_inputs(trip_client):
    def handler(request):
        data = json.loads(request.content)["p_preferences"]
        assert data["departure_city"] == "Riyadh"
        assert data["max_budget_sar"] == "4500.50"
        assert data["available_start"] == data["available_end"]
        return httpx.Response(200, json={**data, "currency": "SAR", "updated_at": None})

    response = trip_client(handler).put(
        f"/api/trips/{TRIP_ID}/preferences",
        json={**PREFERENCES, "available_end": "2026-11-10"},
        headers={"Authorization": "Bearer current-user"},
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    "field", ["departure_city", "max_budget_sar", "available_start", "available_end"]
)
def test_omitted_required_preferences_never_reach_database(trip_client, field):
    body = {key: value for key, value in PREFERENCES.items() if key != field}
    response = trip_client(
        lambda _: pytest.fail("Incomplete input reached database")
    ).put(
        f"/api/trips/{TRIP_ID}/preferences",
        json=body,
        headers={"Authorization": "Bearer current-user"},
    )
    assert response.status_code == 422


def test_preferences_read_still_allows_an_unsaved_form(trip_client):
    response = trip_client(
        lambda _: httpx.Response(
            200,
            json={
                **PREFERENCES,
                "departure_city": "",
                "max_budget_sar": None,
                "available_start": None,
                "available_end": None,
                "updated_at": None,
                "currency": "SAR",
            },
        )
    ).get(
        f"/api/trips/{TRIP_ID}/preferences",
        headers={"Authorization": "Bearer current-user"},
    )
    assert response.status_code == 200
    assert response.json()["updated_at"] is None


@pytest.mark.parametrize(
    ("status", "code", "expected"),
    [
        (403, "42501", 403),
        (404, "PGRST202", 503),
        (400, "23514", 422),
        (401, "invalid_jwt", 401),
    ],
)
def test_preferences_errors_do_not_expose_database_details(
    trip_client, status, code, expected
):
    response = trip_client(
        lambda _: httpx.Response(
            status, json={"code": code, "message": "private input"}
        )
    ).get(
        f"/api/trips/{TRIP_ID}/preferences",
        headers={"Authorization": "Bearer current-user"},
    )
    assert response.status_code == expected
    assert "private input" not in response.text
    if expected == 503:
        assert "preferences migration" in response.json()["detail"]
