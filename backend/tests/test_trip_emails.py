import asyncio
import json
from uuid import uuid4

import httpx2 as httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.services import trip_emails
from app.services.generation_inputs import TripEmail
from app.services.trip_emails import send_trip_email


@pytest.mark.parametrize("revised", [False, True])
def test_gmail_delivery_uses_app_password_and_current_proposal_link(
    monkeypatch, revised
):
    job = TripEmail(
        id=uuid4(),
        lease=uuid4(),
        email="member@example.test",
        trip_id=uuid4(),
        proposal_id=uuid4() if revised else None,
    )
    settings = Settings(
        _env_file=None,
        trip_email_provider="gmail",
        gmail_address="sender@gmail.com",
        gmail_app_password="abcd efgh ijkl mnop",
        trip_app_url="https://rihla.example",
    )
    messages = []

    class SMTP:
        def __init__(self, host, port, timeout, context):
            assert (host, port) == ("smtp.gmail.com", 465)
            assert context.check_hostname

        def login(self, address, password):
            assert address == "sender@gmail.com"
            assert password == "abcdefghijklmnop"

        def send_message(self, message):
            messages.append(message)

        def close(self):
            pass

    monkeypatch.setattr(trip_emails.smtplib, "SMTP_SSL", SMTP)

    async def exercise():
        async with httpx.AsyncClient() as client:
            return await send_trip_email(job, settings, client)

    assert asyncio.run(exercise()) == "sent"
    assert messages[0]["From"] == settings.gmail_address
    assert messages[0]["To"] == job.email
    assert str(job.trip_id) in messages[0].get_content()
    if revised:
        assert f"/proposals/{job.proposal_id}" in messages[0].get_content()
    assert settings.gmail_app_password not in repr(settings)


@pytest.mark.parametrize(
    "error, outcome",
    [
        (trip_emails.smtplib.SMTPAuthenticationError(535, b"invalid"), "retry"),
        (
            trip_emails.smtplib.SMTPRecipientsRefused(
                {"a@example.test": (550, b"unknown")}
            ),
            "failed",
        ),
        (TimeoutError(), "retry"),
    ],
)
def test_gmail_errors_are_safe(monkeypatch, error, outcome):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(trip_emails.smtplib, "SMTP_SSL", fail)
    job = TripEmail(
        id=uuid4(),
        lease=uuid4(),
        email="member@example.test",
        trip_id=uuid4(),
        proposal_id=None,
    )
    settings = Settings(_env_file=None, gmail_address="sender@gmail.com")
    assert trip_emails.send_gmail(job, settings, "subject", "body") == outcome


@pytest.mark.parametrize("revised", [False, True])
def test_email_links_and_retry_identity(revised):
    job = TripEmail(
        id=uuid4(),
        lease=uuid4(),
        email="member@example.test",
        trip_id=uuid4(),
        proposal_id=uuid4() if revised else None,
    )
    settings = Settings(
        _env_file=None,
        trip_email_from="trips@example.test",
        trip_app_url="https://rihla.example/",
        resend_api_key="test-key",
    )
    requests = []
    responses = [None, 429, 503, 200, 422]

    def provider(request):
        requests.append(request)
        status = responses.pop(0)
        if status is None:
            raise httpx.ReadTimeout("ambiguous response", request=request)
        return httpx.Response(status)

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
            return [await send_trip_email(job, settings, client) for _ in range(5)]

    assert asyncio.run(exercise()) == ["retry", "retry", "retry", "sent", "failed"]
    assert len({r.headers["Idempotency-Key"] for r in requests}) == 1
    assert len({r.content for r in requests}) == 1
    assert requests[0].headers["Authorization"] == "Bearer test-key"
    message = json.loads(requests[0].content)
    assert message["to"] == [job.email]
    assert message["from"] == settings.trip_email_from
    link = f"https://rihla.example/trips/{job.trip_id}"
    assert link in message["text"].splitlines()[-1]
    if revised:
        assert f"{link}/proposals/{job.proposal_id}" in message["text"].splitlines()
    else:
        assert "/proposals/" not in message["text"]


def test_enabled_lifespan_claims_and_acknowledges_delivery(monkeypatch):
    app = FastAPI()
    app.state.settings = Settings(
        _env_file=None,
        trip_emails_enabled=True,
        supabase_url="https://db.example",
        supabase_secret_key="fixture",
        trip_email_from="trips@example.test",
        trip_app_url="https://rihla.example",
        resend_api_key="fixture",
    )
    job = TripEmail(
        id=uuid4(),
        lease=uuid4(),
        email="member@example.test",
        trip_id=uuid4(),
        proposal_id=None,
    )

    async def exercise():
        finished = asyncio.Event()
        received = []

        async def claim(settings):
            return job

        async def send(claimed, settings, client):
            return "sent" if claimed == job else "failed"

        async def finish(claimed, outcome, settings):
            received.append((claimed.id, claimed.lease, outcome))
            finished.set()

        monkeypatch.setattr(trip_emails, "claim_trip_email", claim)
        monkeypatch.setattr(trip_emails, "send_trip_email", send)
        monkeypatch.setattr(trip_emails, "finish_trip_email", finish)
        async with trip_emails.email_lifespan(app):
            await asyncio.wait_for(finished.wait(), timeout=3)
        assert received == [(job.id, job.lease, "sent")]

    asyncio.run(exercise())
