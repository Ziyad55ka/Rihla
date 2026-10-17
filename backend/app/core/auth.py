"""Identity comes from Supabase Auth, never from browser-supplied user IDs."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError

from app.schemas.accounts import Account
from app.services.supabase import SupabaseHTTP, supabase_request

bearer = HTTPBearer(auto_error=False)


def invalid_token() -> HTTPException:
    return HTTPException(
        401,
        "Your session is invalid or expired. Sign in again.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_access_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise invalid_token()
    return credentials.credentials


AccessToken = Annotated[str, Depends(get_access_token)]


@dataclass(frozen=True)
class Identity:
    account: Account
    access_token: str


async def get_identity(token: AccessToken, client: SupabaseHTTP) -> Identity:
    # GET /user authoritatively verifies signature/expiry/project via Auth.
    # No decoding-only checks, shared sessions, or JWT signing secrets are needed.
    response = await supabase_request(client, "GET", "auth/v1/user", token)
    if response.status_code in (401, 403):
        raise invalid_token()
    if response.status_code != 200:
        raise HTTPException(503, "Supabase could not verify the session. Try again.")
    try:
        payload = response.json()
        account = Account.model_validate(payload)
        if payload.get("is_anonymous", False) or not account.email:
            raise invalid_token()
    except (ValueError, ValidationError) as error:
        raise HTTPException(
            503, "Supabase returned an invalid account response."
        ) from error
    return Identity(account=account, access_token=token)


CurrentIdentity = Annotated[Identity, Depends(get_identity)]
