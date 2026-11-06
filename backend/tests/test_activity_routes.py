import json
from pathlib import Path

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
def activity_api(monkeypatch):
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
    app.state.settings.place_images_enabled = False
    proposal = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "backend/tests/fixtures/activities.json"
        ).read_text(encoding="utf-8")
    )["proposals"][0]
    proposal.update(id=PROPOSAL, trip_id=TRIP)
    proposal["cities"][0]["activities"][0]["id"] = ACTIVITY
    from app.services.generation_inputs import FlightContext

    async def context(*args, **kwargs):
        return FlightContext(
            city="Riyadh", adults=1, ceiling="10000", proposal=proposal
        )

    monkeypatch.setattr("app.api.routes.activities.fetch_flight_context", context)

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
            if request.url.path.endswith("/rihla_get_activity_costs"):
                return httpx.Response(
                    200,
                    json={
                        "proposals": [
                            {
                                "id": PROPOSAL,
                                "activity_ids": [ACTIVITY],
                                "group_cost": {
                                    "amount_sar": "85.50",
                                    "status": "Estimated",
                                    "partial": False,
                                },
                            }
                        ]
                    },
                )
            if request.url.path.endswith("/rihla_get_proposals"):
                return httpx.Response(
                    200,
                    json={
                        "version": 1,
                        "complete": True,
                        "generated_at": None,
                        "generating": False,
                        "needs_regeneration": answer.get("needs_regeneration", False),
                        "proposals": [proposal],
                    },
                )
            if "raw" in answer:
                return httpx.Response(answer["status"], text=answer["raw"])
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


@pytest.mark.parametrize("ceiling,expected", [("2035.50", 200), ("2035.49", 422)])
def test_group_minimum_budget_is_checked_before_any_selection_write(
    activity_api, monkeypatch, ceiling, expected
):
    from app.services.generation_inputs import FlightContext

    client, calls, _ = activity_api
    body = client.get(f"/api/trips/{TRIP}/proposals").json()["proposals"][0]

    async def context(*args, **kwargs):
        return FlightContext(city="Riyadh", adults=1, ceiling=ceiling, proposal=body)

    monkeypatch.setattr("app.api.routes.activities.fetch_flight_context", context)
    calls.clear()
    response = client.put(URL, json={"version": 1, "activity_ids": [ACTIVITY]})
    assert response.status_code == expected
    writes = [p for p, _ in calls if p.endswith("rihla_set_activity_selection")]
    assert bool(writes) == (expected == 200)
    if expected == 422:
        assert ceiling not in response.text


def test_cannot_save_if_private_group_budget_cannot_be_verified(
    activity_api, monkeypatch
):
    from app.services.generation_inputs import GenerationInputsError

    client, calls, _ = activity_api

    async def unavailable(*args, **kwargs):
        raise GenerationInputsError("unavailable")

    monkeypatch.setattr("app.api.routes.activities.fetch_flight_context", unavailable)
    response = client.put(URL, json={"version": 1, "activity_ids": []})
    assert response.status_code == 503
    assert not any(p.endswith("rihla_set_activity_selection") for p, _ in calls)


@pytest.mark.parametrize(
    "message,status,text",
    [
        ("activity_budget_exceeded", 422, "exceed the group's budget"),
        ("activity_budget_unavailable", 503, "verify the group budget"),
    ],
)
def test_database_budget_guard_has_an_actionable_error(
    activity_api, message, status, text
):
    client, _, answer = activity_api
    answer.update(status=400, body={"code": "23514", "message": message})
    response = client.put(URL, json={"version": 1, "activity_ids": []})
    assert response.status_code == status and text in response.json()["detail"]


def test_non_json_storage_failure_does_not_crash_the_error_handler(activity_api):
    client, _, answer = activity_api
    answer.update(status=503, raw="<html>source unavailable</html>")
    response = client.get(URL)
    assert response.status_code == 503
    assert "Activity storage is unavailable" in response.json()["detail"]


def test_stale_preference_snapshot_can_be_read_but_not_saved(activity_api):
    client, calls, answer = activity_api
    answer["needs_regeneration"] = True
    assert client.get(URL).status_code == 200
    response = client.put(URL, json={"version": 1, "activity_ids": []})
    assert response.status_code == 409
    assert not any(path.endswith("rihla_set_activity_selection") for path, _ in calls)


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
    estimate = response.json()["estimate"]
    assert estimate["activities"]["known_amount_sar"] == "85.50"
    assert estimate["total"]["known_amount_sar"] == "2035.50"
    assert estimate["meals"]["known_amount_sar"] == "750.00"
    assert estimate["accommodation"]["missing_items"] > 0


def test_main_proposal_response_includes_saved_activity_costs(activity_api):
    client, _, _ = activity_api
    response = client.get(f"/api/trips/{TRIP}/proposals")
    assert response.status_code == 200
    costs = response.json()["costs"][0]
    assert "activities_selected" in costs["assumptions"]
    activity_line = next(
        part
        for part in costs["scenarios"][0]["lines"]
        if part["category"] == "activities"
    )
    assert activity_line["counted"]
    assert activity_line["per_person"]["amount_sar"] == "85.50"
    selection = client.get(URL).json()["estimate"]
    assert (
        selection["total"]["known_amount_sar"]
        == costs["scenarios"][0]["per_person_total"]["amount_sar"]
    )


def test_real_suggestions_require_provider_setup_and_verified_session(activity_api):
    client, _, _ = activity_api
    endpoint = URL.replace("/selection", "/suggestions")
    assert client.post(endpoint, json={"version": 1}).status_code == 503
    client.headers.pop("Authorization")
    assert client.post(endpoint, json={"version": 1}).status_code == 401


def test_cached_suggestions_do_not_spend_provider_requests(activity_api, monkeypatch):
    from app.api.routes import activity_suggestions as routes

    client, _, _ = activity_api
    client.app.state.settings.gemini_api_key = "test"
    client.app.state.settings.tavily_api_key = "test"
    calls = []

    async def rpc(name, args, settings, transport):
        calls.append((name, args))
        return httpx.Response(200, json={"ready": True, "started": False})

    monkeypatch.setattr(routes, "_secret_rpc", rpc)
    endpoint = URL.replace("/selection", "/suggestions")
    assert client.post(endpoint, json={"version": 1}).json() == {"ready": True}
    assert len(calls) == 1
    assert calls[0][1]["p_user_id"] == "11111111-1111-4111-8111-111111111111"
    assert (
        client.post(endpoint, json={"version": 1, "p_user_id": TRIP}).status_code == 422
    )


def test_suggestions_save_checked_data_and_release_failed_jobs(
    activity_api, monkeypatch
):
    from activity_fixture import mock_data

    from app.api.routes import activity_suggestions as routes
    from app.schemas.proposals import Proposal
    from app.services.trip_research import ResearchError

    client, _, _ = activity_api
    client.app.state.settings.gemini_api_key = "test"
    client.app.state.settings.tavily_api_key = "test"
    calls = []
    proposal = mock_data()["proposals"][0]

    async def rpc(name, args, settings, transport):
        calls.append((name, args))
        return httpx.Response(
            200, json={"ready": False, "started": True, "proposal": proposal}
        )

    async def find(p, settings):
        return Proposal.model_validate(p.model_dump())

    monkeypatch.setattr(routes, "_secret_rpc", rpc)
    monkeypatch.setattr(routes, "find_activities", find)
    endpoint = URL.replace("/selection", "/suggestions")
    assert client.post(endpoint, json={"version": 1}).status_code == 200
    assert [c[0] for c in calls] == [
        "rihla_begin_activity_research",
        "rihla_finish_activity_research",
        "rihla_fail_activity_research",
    ]

    async def fail(p, settings):
        raise ResearchError("model_quota", "Quota reached")

    calls.clear()
    monkeypatch.setattr(routes, "find_activities", fail)
    assert client.post(endpoint, json={"version": 1}).status_code == 503
    assert [c[0] for c in calls] == [
        "rihla_begin_activity_research",
        "rihla_fail_activity_research",
    ]


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


def test_removing_all_choices_returns_updated_proposal_estimate(activity_api):
    client, _, answer = activity_api
    answer["body"]["activity_ids"] = []
    response = client.put(URL, json={"version": 1, "activity_ids": []})
    assert response.status_code == 200
    assert response.json()["estimate"]["activities"]["known_amount_sar"] == "0.00"
    assert response.json()["estimate"]["total"]["known_amount_sar"] == "1950.00"


def test_stale_version_or_foreign_activity_is_rejected_before_save(activity_api):
    client, calls, _ = activity_api
    response = client.put(URL, json={"version": 2, "activity_ids": []})
    assert response.status_code == 409
    response = client.put(URL, json={"version": 1, "activity_ids": [TRIP]})
    assert response.status_code == 422
    assert not any(path.endswith("/rihla_set_activity_selection") for path, _ in calls)


@pytest.mark.parametrize(
    ("code", "message"),
    [
        (
            "model_quota",
            "The AI request limit has been reached. "
            "Retry timing depends on the service limit.",
        ),
        ("search_quota", "Today's search allowance has run out. Try again later."),
        ("model_unavailable", "Activity search is unavailable. Try again later."),
    ],
)
def test_suggestion_failures_name_a_spent_allowance(
    activity_api, monkeypatch, code, message
):
    from activity_fixture import mock_data

    from app.api.routes import activity_suggestions as routes
    from app.services.trip_research import ResearchError

    client, _, _ = activity_api
    client.app.state.settings.gemini_api_key = "test"
    client.app.state.settings.tavily_api_key = "test"
    proposal = mock_data()["proposals"][0]

    async def rpc(name, args, settings, transport):
        return httpx.Response(
            200, json={"ready": False, "started": True, "proposal": proposal}
        )

    async def fail(p, settings):
        raise ResearchError(code, "provider detail that is never shown")

    monkeypatch.setattr(routes, "_secret_rpc", rpc)
    monkeypatch.setattr(routes, "find_activities", fail)
    response = client.post(
        URL.replace("/selection", "/suggestions"), json={"version": 1}
    )
    assert response.status_code == 503
    assert response.json()["detail"] == message
