from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.core.auth import CurrentIdentity, invalid_token
from app.schemas.accounts import Account, Profile, ProfileInput
from app.services.supabase import SupabaseHTTP, supabase_request

router = APIRouter(prefix="/api", tags=["accounts"])


@router.get("/me", response_model=Account)
async def current_account(identity: CurrentIdentity) -> Account:
    return identity.account


async def profile_request(
    client: SupabaseHTTP,
    identity: CurrentIdentity,
    method: str,
    body: dict[str, str] | None = None,
) -> Profile | None:
    # Explicit owner filter and RLS both apply. Never accept an owner from the UI.
    params = {"select": "id,display_name,created_at"}
    if method == "POST":
        params["on_conflict"] = "id"
    else:
        params["id"] = f"eq.{identity.account.id}"
    response = await supabase_request(
        client,
        method,
        "rest/v1/profiles",
        identity.access_token,
        params=params,
        json=body,
        extra_headers={"Prefer": "resolution=merge-duplicates,return=representation"},
    )
    if response.status_code == 401:
        raise invalid_token()
    if response.status_code == 403:
        raise HTTPException(403, "Profile access was denied by database permissions.")
    if response.status_code not in (200, 201):
        raise HTTPException(
            503,
            "Profile storage is unavailable. Check the account migration and grants.",
        )
    try:
        rows = response.json()
        if not isinstance(rows, list) or len(rows) > 1:
            raise ValueError("Invalid profile result")
        if not rows and method == "GET":
            return None
        profile = Profile.model_validate(rows[0])
        if profile.id != identity.account.id:
            raise ValueError("Unexpected profile owner")
        return profile
    except (ValueError, ValidationError, IndexError) as error:
        raise HTTPException(
            503, "Supabase returned an invalid profile response."
        ) from error


@router.get("/profile", response_model=Profile | None)
async def read_profile(
    identity: CurrentIdentity, client: SupabaseHTTP
) -> Profile | None:
    return await profile_request(client, identity, "GET")


@router.put("/profile", response_model=Profile)
async def save_profile(
    body: ProfileInput,
    identity: CurrentIdentity,
    client: SupabaseHTTP,
) -> Profile | None:
    return await profile_request(
        client,
        identity,
        "POST",
        {"id": str(identity.account.id), "display_name": body.display_name},
    )
