import json

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.supabase import get_supabase_http

TRIP = "44444444-4444-4444-8444-444444444444"
PROPOSAL = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
ACTIVITY = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
URL = f"/api/trips/{TRIP}/proposals/{PROPOSAL}/activities/selection"


@pytest.fixture
def activity_api():
    calls = []
    answer = {
        "status": 200,
        "body": {
            "proposal_id": PROPOSAL,
            "version": 1,
            "activity_ids": [ACTIVITY],
        },
    }
    app = create_app(Settings(_env_file=None, app_env="test"))

    async def fake_http():
        def upstream(request):
            if request.url.path == "/auth/v1/user":
                return httpx.Response(
                    200,
                    json={
                        "id": "11111111-1111-4111-8111-111111111111",
                        "email": "test@example.test",
                    },
                )
            calls.append((request.url.path, json.loads(request.content)))
            return httpx.Response(answer["status"], json=answer["body"])

        async with httpx.AsyncClient(
            base_url="https://supabase.example/",
            transport=httpx.MockTransport(upstream),
        ) as client:
            yield client

    app.dependency_overrides[get_supabase_http] = fake_http
    client = TestClient(app)
    client.headers["Authorization"] = "Bearer current-user"
    return client, calls, answer


def test_read_and_save_forward_only_verified_identity(activity_api):
    client, calls, _ = activity_api
    assert client.get(URL).json()["activity_ids"] == [ACTIVITY]
    response = client.put(URL, json={"version": 1, "activity_ids": [ACTIVITY]})
    assert response.status_code == 200
    assert calls[-1] == (
        "/rest/v1/rpc/rihla_set_activity_selection",
        {
            "p_trip_id": TRIP,
            "p_proposal_id": PROPOSAL,
            "p_version": 1,
            "p_activity_ids": [ACTIVITY],
        },
    )


def test_anonymous_and_forged_owner_requests_cannot_save(activity_api):
    client, calls, _ = activity_api
    assert (
        client.put(
            URL,
            json={
                "version": 1,
                "activity_ids": [],
                "user_id": TRIP,
            },
        ).status_code
        == 422
    )
    assert calls == []
    client.headers.pop("Authorization")
    assert client.get(URL).status_code == 401


@pytest.mark.parametrize(
    "code,status", [("42501", 403), ("P0001", 409), ("23514", 422)]
)
def test_selection_errors_have_actionable_statuses(activity_api, code, status):
    client, _, answer = activity_api
    answer.update(status=400, body={"code": code})
    assert (
        client.put(URL, json={"version": 1, "activity_ids": []}).status_code == status
    )
