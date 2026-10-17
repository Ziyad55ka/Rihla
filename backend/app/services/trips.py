import httpx2 as httpx
from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError

from app.core.auth import Identity, invalid_token
from app.services.supabase import supabase_request


async def trip_rpc[T](
    client: httpx.AsyncClient, identity: Identity, name: str, args: dict, model: type[T]
) -> T:
    # Name is chosen by server routes, never accepted from user input.
    response = await supabase_request(
        client, "POST", f"rest/v1/rpc/{name}", identity.access_token, json=args
    )
    if response.status_code == 401:
        raise invalid_token()
    if response.status_code not in (200, 201):
        try:
            error = response.json()
            code = error.get("code") if isinstance(error, dict) else None
        except ValueError:
            code = None
        if code == "P0001" and name == "rihla_join_trip":
            raise HTTPException(404, "This invitation is invalid, expired or revoked.")
        if response.status_code == 403 or code == "42501":
            raise HTTPException(403, "You do not have permission for this trip action.")
        preferences = name in {"rihla_get_preferences", "rihla_save_preferences"}
        if code in {"23514", "23502", "22001", "22003", "22007", "22008", "22P02"}:
            if preferences:
                raise HTTPException(422, "Check the preference values and date order.")
            raise HTTPException(422, "Check the trip title and description.")
        if preferences:
            raise HTTPException(
                503,
                "Preference storage is unavailable. "
                "Check that the preferences migration is applied.",
            )
        if name == "rihla_get_planning_status":
            raise HTTPException(
                503,
                "Planning status is unavailable. "
                "Check that the readiness migration is applied.",
            )
        raise HTTPException(
            503,
            "Trip storage is unavailable. Check that the trips migration is applied.",
        )
    try:
        return TypeAdapter(model).validate_python(response.json())
    except (ValueError, ValidationError) as error:
        raise HTTPException(
            503, "Trip storage returned an invalid response."
        ) from error
