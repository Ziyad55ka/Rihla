import asyncio
from types import SimpleNamespace

import httpx2 as httpx
import openai
import pytest
from pydantic import BaseModel

from app.core.config import Settings
from app.services import trip_research
from app.services.trip_research import ResearchCost, ResearchError, call_gemini


class Inner(BaseModel):
    name: str


class Answer(BaseModel):
    city: str
    items: list[Inner]


def settings(**extra) -> Settings:
    return Settings(
        _env_file=None,
        openrouter_api_key="sk-or-test",
        gemini_model="gemini-3.6-flash",
        gemini_retry_delay_seconds=0,
        **extra,
    )


def fake_client(monkeypatch, outcomes: list, seen: list) -> None:
    class Completions:
        async def create(self, **kwargs):
            seen.append(kwargs)
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=outcome))],
                usage=SimpleNamespace(total_tokens=42),
            )

    class Client:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=Completions())

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr(trip_research.openai, "AsyncOpenAI", Client)


def status_error(code: int) -> openai.APIStatusError:
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx.Response(code, request=request)
    return openai.APIStatusError("x", response=response, body=None)


def test_openrouter_returns_checked_json(monkeypatch) -> None:
    seen: list = []
    fake_client(
        monkeypatch, ['```json\n{"city":"Kyoto","items":[{"name":"a"}]}\n```'], seen
    )
    cost = ResearchCost()
    answer = asyncio.run(
        call_gemini(
            "x",
            "y",
            Answer,
            settings(openrouter_provider="google-ai-studio"),
            cost,
            "low",
        )
    )
    assert answer.city == "Kyoto"
    assert cost.gemini_requests == 1 and cost.gemini_tokens == 42
    request = seen[0]
    assert request["model"] == "google/gemini-3.6-flash"
    assert request["extra_body"]["reasoning"]["effort"] == "low"
    assert request["extra_body"]["provider"]["only"] == ["google-ai-studio"]
    assert "$ref" not in str(request["response_format"])


def test_extractor_model_is_used_for_extraction() -> None:
    chosen = settings(
        openrouter_model="google/gemini-3.6-flash",
        gemini_extractor_model="gemini-3.5-flash-lite",
    )
    assert chosen.openrouter_model_id() == "google/gemini-3.6-flash"
    assert (
        chosen.for_extraction().openrouter_model_id() == "google/gemini-3.5-flash-lite"
    )


@pytest.mark.parametrize(
    ("code", "reason"), [(401, "not_configured"), (402, "model_quota")]
)
def test_key_and_credit_errors_stop_at_once(monkeypatch, code, reason) -> None:
    seen: list = []
    fake_client(monkeypatch, [status_error(code)], seen)
    with pytest.raises(ResearchError) as error:
        asyncio.run(call_gemini("x", "y", Answer, settings(), ResearchCost()))
    assert error.value.code == reason and len(seen) == 1


def test_busy_model_is_retried_once(monkeypatch) -> None:
    seen: list = []
    fake_client(monkeypatch, [status_error(503), '{"city":"Oslo","items":[]}'], seen)
    answer = asyncio.run(call_gemini("x", "y", Answer, settings(), ResearchCost()))
    assert answer.city == "Oslo" and len(seen) == 2
