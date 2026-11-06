"""Plain-text model call through OpenRouter, for small scripts and experiments.

The app itself uses trip_research.call_gemini, which returns checked JSON.
"""

from openai import OpenAI

from app.core.config import Settings


def ask(prompt: str, system: str | None = None) -> str:
    settings = Settings()
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured.")
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1", api_key=settings.openrouter_api_key
    )
    messages = [{"role": "system", "content": system}] if system else []
    messages.append({"role": "user", "content": prompt})
    extra = (
        {"provider": {"only": [settings.openrouter_provider], "allow_fallbacks": False}}
        if settings.openrouter_provider
        else None
    )
    response = client.chat.completions.create(
        model=settings.openrouter_model_id(), messages=messages, extra_body=extra
    )
    return response.choices[0].message.content or ""
