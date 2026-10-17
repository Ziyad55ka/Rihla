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
            and isinstance(payload, dict)
            and payload.get("code") == "invalid_credentials"
        ):
            outcome = "invalid"
            session = None
        elif isinstance(payload, dict) and payload.get("code") == "email_not_confirmed":
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
