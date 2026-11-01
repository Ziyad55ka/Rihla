"""The book and refresh routes, with the database and Ignav replaced by fakes."""

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from test_flight_refresh import TRIP, FakeIgnav, proposal

from app.api.routes import proposals as routes
from app.core.auth import get_identity
from app.core.config import Settings
from app.main import create_app
from app.services.generation_inputs import FlightContext, GenerationInputsError

PROPOSAL = "00000000-0000-4000-8000-0000000000bb"
MEMBER = UUID("00000000-0000-4000-8000-0000000000cc")


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    settings = Settings(
        _env_file=None,
        app_env="test",
        ignav_api_key="fake",
        flight_usage_db=tmp_path / "usage.sqlite3",
    )
    app = create_app(settings)
    app.dependency_overrides[get_identity] = lambda: SimpleNamespace(
        account=SimpleNamespace(id=MEMBER), access_token="t"
    )
    saved: list = []

    async def context(trip_id, proposal_id, member_id, config):
        assert member_id == MEMBER
        return FlightContext(
            city="الرياض", adults=2, ceiling=Decimal(5000), proposal=proposal()
        )

    async def save(trip_id, proposal_id, member_id, flights, status, config):
        saved.append((member_id, flights, status))

    original = routes.FlightChecker

    monkeypatch.setattr(routes, "fetch_flight_context", context)
    monkeypatch.setattr(routes, "save_flight_refresh", save)
    monkeypatch.setattr(
        routes, "FlightChecker", lambda config: original(config, FakeIgnav())
    )
    return TestClient(app), saved


def test_book_returns_a_fresh_link_and_no_private_count(api) -> None:
    client, _ = api

    response = client.get(
        f"/api/trips/{TRIP}/proposals/{PROPOSAL}/book-flight?leg=round_trip"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["url"] == "https://www.gulfair.com/book?x=1"
    assert body["fallback"] is None
    assert Decimal(body["price_sar"]) == Decimal(950)
    assert Decimal(body["previous_price_sar"]) == Decimal(900)
    assert "adults" not in body and "ceiling" not in body


def test_book_rejects_an_unknown_leg(api) -> None:
    client, _ = api

    response = client.get(
        f"/api/trips/{TRIP}/proposals/{PROPOSAL}/book-flight?leg=everything"
    )

    assert response.status_code == 422


def test_refresh_saves_only_for_the_verified_account(api) -> None:
    client, saved = api

    response = client.post(f"/api/trips/{TRIP}/proposals/{PROPOSAL}/refresh-flights")

    assert response.status_code == 200
    assert response.json()["updated"] is True
    assert response.json()["now_over_budget"] is False
    assert response.json()["next_refresh_seconds"] == 300
    assert saved[0][0] == MEMBER
    assert saved[0][1].price_per_person.amount_sar == Decimal("950.00")


@pytest.mark.parametrize(
    ("code", "status"), [("access_denied", 403), ("proposal_not_found", 404)]
)
def test_outsiders_and_replaced_proposals_are_refused(
    api, monkeypatch: pytest.MonkeyPatch, code: str, status: int
) -> None:
    client, _ = api

    async def refuse(*args):
        raise GenerationInputsError(code)

    monkeypatch.setattr(routes, "fetch_flight_context", refuse)

    assert (
        client.get(
            f"/api/trips/{TRIP}/proposals/{PROPOSAL}/book-flight?leg=outbound"
        ).status_code
        == status
    )
    assert (
        client.post(
            f"/api/trips/{TRIP}/proposals/{PROPOSAL}/refresh-flights"
        ).status_code
        == status
    )


def test_a_city_with_no_flights_gets_not_found(
    api, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = api

    async def other_city(*args):
        return FlightContext(
            city="جدة", adults=1, ceiling=Decimal(5000), proposal=proposal()
        )

    monkeypatch.setattr(routes, "fetch_flight_context", other_city)

    response = client.get(
        f"/api/trips/{TRIP}/proposals/{PROPOSAL}/book-flight?leg=round_trip"
    )

    assert response.status_code == 404
