import httpx2 as httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from app.services.login_limits import LoginLimits, limited
from app.services.supabase import SupabaseHTTP

router = APIRouter(prefix="/api/auth", tags=["accounts"])


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(
        min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
    )
    password: SecretStr = Field(min_length=1, max_length=128)


class LoginSession(BaseModel):
    access_token: str = Field(min_length=1)
    refresh_token: str = Field(min_length=1)


def auth_error_code(payload: object) -> str | None:
    """Supabase Auth's reason. Newer versions put it in error_code and the
    HTTP status in code; older ones used code, or error=invalid_grant."""
    if not isinstance(payload, dict):
        return None
    for key in ("error_code", "code"):
        if isinstance(payload.get(key), str):
            return payload[key]
    if payload.get("error") == "invalid_grant":
        detail = str(payload.get("error_description") or "").casefold()
        if "not confirmed" in detail:
            return "email_not_confirmed"
        if "invalid login credentials" in detail:
            return "invalid_credentials"
    return None


@router.post("/login", response_model=LoginSession)
async def login(body: LoginInput, request: Request, client: SupabaseHTTP):
    limits = LoginLimits(request.app.state.settings.login_limit_db)
    email = body.email.strip().lower()
    lease = await run_in_threadpool(limits.reserve, email)
    outcome = "other"
    try:
        # No user token exists yet. The request-scoped client supplies only the
        # publishable API key; passwords are verified exclusively by Supabase.
        try:
            response = await client.post(
                "auth/v1/token",
                params={"grant_type": "password"},
                json={"email": email, "password": body.password.get_secret_value()},
            )
            payload = response.json()
        except (httpx.RequestError, ValueError) as error:
            raise HTTPException(
                503, "Sign-in service is unavailable. Try again."
            ) from error
        if response.status_code == 200:
            try:
                session = LoginSession.model_validate(payload)
            except ValidationError as error:
                raise HTTPException(
                    503, "Sign-in service returned an invalid response."
                ) from error
            outcome = "success"
        elif (
            response.status_code in (400, 401)
            and auth_error_code(payload) == "invalid_credentials"
        ):
            outcome = "invalid"
            session = None
        elif response.status_code < 500 and (
            auth_error_code(payload) == "email_not_confirmed"
        ):
            raise HTTPException(
                403,
                {
                    "code": "email_not_confirmed",
                    "message": "Confirm your email before signing in.",
                },
            )
        elif response.status_code == 429:
            raise limited(60, "over_request_rate_limit")
        else:
            raise HTTPException(503, "Sign-in service is unavailable. Try again.")
    finally:
        blocked = await run_in_threadpool(limits.complete, lease, outcome)
    if blocked:
        raise limited(blocked)
    if session is None:
        raise HTTPException(
            401,
            {
                "code": "invalid_credentials",
                "message": "The email or password is incorrect.",
            },
        )
    return session
