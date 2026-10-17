from fastapi.testclient import TestClient


def test_health_is_available_without_auth_or_supabase(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ok", "service": "rihla-api"}


def test_health_allows_the_configured_frontend_origin(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-credentials" not in response.headers


def test_health_does_not_allow_an_unlisted_origin(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": "https://unlisted.example"})

    # CORS governs browser access; the public endpoint can still return data.
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_preflight_allows_authorization_header(client: TestClient) -> None:
    response = client.options(
        "/health",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_preflight_rejects_an_unlisted_origin(client: TestClient) -> None:
    response = client.options(
        "/health",
        headers={
            "Origin": "https://unlisted.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
