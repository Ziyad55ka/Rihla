"""Route tests. Supabase, Gemini, Tavily and Ignav are all fake here."""

import json

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient

from app.api.routes import proposals as routes
from app.core.config import Settings
from app.main import create_app
from app.schemas.generation import GenerationInput
from app.services.generation_inputs import GenerationInputsError
from app.services.proposal_generation import GenerationBlocked, GenerationResult
from app.services.supabase import get_supabase_http
from app.services.trip_research import ResearchCost, ResearchError

USER = "11111111-1111-4111-8111-111111111111"
TRIP = "44444444-4444-4444-8444-444444444444"
CLEAR = {"conflicts": [], "own_review": [], "can_generate": True}
STORED = {
    "version": 1,
    "complete": True,
    "generated_at": "2026-11-02T00:00:00Z",
    "generating": False,
    "proposals": [],
}
INPUT = GenerationInput(
    trip_id=TRIP,
    shared_start="2026-12-13",
    shared_end="2026-12-17",
    members=[
        {"label": "Member 1", "departure_city": "Riyadh", "max_budget_sar": "4000"}
    ],
)


def result(**update) -> GenerationResult:
    base = GenerationResult(
        proposals=[], complete=True, message=None, failures=[], cost=ResearchCost()
    )
    return base.model_copy(update=update)


@pytest.fixture
def rpc_log() -> list[str]:
    return []


@pytest.fixture
def api(tmp_path, rpc_log):
    def build(**answers) -> TestClient:
        responses = {
            "rihla_begin_proposal_generation": httpx.Response(
                200, json={"started": True, "version": 1}
            ),
            "rihla_end_proposal_generation": httpx.Response(200, json={"ended": True}),
            "rihla_get_group_conflicts": httpx.Response(200, json=CLEAR),
            "rihla_get_proposals": httpx.Response(200, json=STORED),
            **answers,
        }
        app = create_app(
            Settings(
                _env_file=None,
                app_env="test",
                generation_store_db=tmp_path / "store.sqlite3",
            )
        )

        async def fake_http():
            def upstream(request: httpx.Request) -> httpx.Response:
                if request.url.path == "/auth/v1/user":
                    return httpx.Response(
                        200, json={"id": USER, "email": "test@example.test"}
                    )
                name = request.url.path.rsplit("/", 1)[1]
                rpc_log.append(name)
                return responses[name]

            async with httpx.AsyncClient(
                base_url="https://supabase.example/",
                transport=httpx.MockTransport(upstream),
            ) as client:
                yield client

        app.dependency_overrides[get_supabase_http] = fake_http
        client = TestClient(app)
        client.headers["Authorization"] = "Bearer current-user"
        return client

    return build


@pytest.fixture
def pipeline(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Replace the private read and generation, recording how they were called."""
    calls: dict = {"fetch": [], "generate": []}

    async def fetch(trip_id, admin_id, settings):
        calls["fetch"].append(str(admin_id))
        return INPUT

    async def generate(generation, settings, **kwargs):
        calls["generate"].append(kwargs)
        return result()

    monkeypatch.setattr(routes, "fetch_generation_inputs", fetch)
    monkeypatch.setattr(routes, "generate_checked", generate)
    return calls


def post(client: TestClient, body=None):
    return client.post(f"/api/trips/{TRIP}/proposals", json=body)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", f"/api/trips/{TRIP}/conflicts"),
        ("GET", f"/api/trips/{TRIP}/proposals"),
        ("POST", f"/api/trips/{TRIP}/proposals"),
    ],
)
def test_routes_require_authentication(client, method, path) -> None:
    assert client.request(method, path).status_code == 401


@pytest.mark.parametrize("body", [None, {"regenerate": True}])
def test_non_admin_is_refused_before_any_private_read_or_quota(
    api, pipeline, rpc_log, body
) -> None:
    denied = httpx.Response(403, json={"code": "42501"})

    response = post(api(rihla_begin_proposal_generation=denied), body)

    assert response.status_code == 403
    assert pipeline == {"fetch": [], "generate": []}
    assert rpc_log == ["rihla_begin_proposal_generation"]


def test_second_generation_for_the_same_trip_is_refused(api, pipeline) -> None:
    busy = httpx.Response(200, json={"started": False, "version": None})

    response = post(api(rihla_begin_proposal_generation=busy))

    assert response.status_code == 409
    assert "already being generated" in response.json()["detail"]
    assert pipeline["generate"] == []


def test_conflicts_stop_generation_with_categories_only(api, pipeline, rpc_log) -> None:
    conflict = httpx.Response(
        200,
        json={
            "conflicts": ["destinations", "budget"],
            "own_review": [],
            "can_generate": False,
        },
    )

    response = post(api(rihla_get_group_conflicts=conflict))

    assert response.status_code == 409
    assert response.json()["detail"]["categories"] == ["destinations", "budget"]
    assert pipeline == {"fetch": [], "generate": []}
    assert rpc_log[-1] == "rihla_end_proposal_generation"


def test_verified_admin_generates_and_reads_back_through_the_filter(
    api, pipeline, rpc_log
) -> None:
    response = post(api())

    assert response.status_code == 200
    assert pipeline["fetch"] == [USER]
    assert pipeline["generate"][0]["regenerate"] is False
    assert pipeline["generate"][0]["version"] == 1
    assert rpc_log[-1] == "rihla_get_proposals"
    assert response.json()["reused"] is False


def test_regenerate_is_passed_on_for_the_admin(api, pipeline) -> None:
    assert post(api(), {"regenerate": True}).status_code == 200
    assert pipeline["generate"][0]["regenerate"] is True


def test_request_body_cannot_choose_the_admin(api, pipeline) -> None:
    assert post(api(), {"admin_id": "someone-else"}).status_code == 422
    assert pipeline["fetch"] == []


@pytest.mark.parametrize(
    ("failure", "status", "text"),
    [
        (GenerationBlocked("budget"), 409, "budget"),
        (ResearchError("model_quota", "x"), 503, "allowance"),
        (ResearchError("search_quota", "x"), 503, "allowance"),
        (ResearchError("model_unavailable", "secret detail"), 503, "temporarily"),
        (GenerationInputsError("not_ready"), 409, "ready"),
        (GenerationInputsError("access_denied"), 403, "permission"),
        (GenerationInputsError("not_configured"), 503, "not set up"),
    ],
)
def test_failures_are_clear_and_always_release_the_lock(
    api, pipeline, monkeypatch, rpc_log, failure, status, text
) -> None:
    async def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(routes, "generate_checked", fail)

    response = post(api())

    assert response.status_code == status
    assert text in json.dumps(response.json())
    assert "secret detail" not in response.text
    assert rpc_log[-1] == "rihla_end_proposal_generation"


def test_any_member_can_read_conflicts_and_proposals(api, rpc_log) -> None:
    client = api()

    assert client.get(f"/api/trips/{TRIP}/conflicts").json() == CLEAR
    assert client.get(f"/api/trips/{TRIP}/proposals").json()["version"] == 1
    assert rpc_log == ["rihla_get_group_conflicts", "rihla_get_proposals"]


def test_non_member_cannot_read_proposals(api) -> None:
    denied = httpx.Response(403, json={"code": "42501"})

    assert (
        api(rihla_get_proposals=denied).get(f"/api/trips/{TRIP}/proposals").status_code
        == 403
    )
