"""Small, request-scoped Supabase HTTP integration; no privileged key or session."""

from collections.abc import AsyncIterator
from typing import Annotated

import httpx2 as httpx
from fastapi import Depends, HTTPException, Request


async def get_supabase_http(request: Request) -> AsyncIterator[httpx.AsyncClient]:
    settings = request.app.state.settings
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise HTTPException(503, "Supabase is not configured on the backend.")
    async with httpx.AsyncClient(
        base_url=settings.supabase_url.rstrip("/") + "/",
        headers={"apikey": settings.supabase_publishable_key},
        timeout=5.0,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        yield client


SupabaseHTTP = Annotated[httpx.AsyncClient, Depends(get_supabase_http)]


async def supabase_request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    token: str,
    extra_headers: dict[str, str] | None = None,
    **kwargs: object,
) -> httpx.Response:
    try:
        return await client.request(
            method,
            path,
            headers={**(extra_headers or {}), "Authorization": f"Bearer {token}"},
            **kwargs,
        )
    except httpx.RequestError as error:
        # Never return upstream messages, tokens or credentials to the browser.
        raise HTTPException(
            503, "Supabase is temporarily unavailable. Try again."
        ) from error
