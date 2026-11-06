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
        error = None
        try:
            error = response.json()
            code = error.get("code") if isinstance(error, dict) else None
        except ValueError:
            code = None
        if code == "P0001" and name == "rihla_join_trip":
            raise HTTPException(404, "This invitation is invalid, expired or revoked.")
        if response.status_code == 403 or code == "42501":
            raise HTTPException(403, "You do not have permission for this trip action.")
        if name in {"rihla_get_activity_selection", "rihla_set_activity_selection"}:
            message = error.get("message") if isinstance(error, dict) else None
            if code == "23514" and message == "activity_budget_exceeded":
                raise HTTPException(
                    422,
                    "These activities exceed the group's budget. "
                    "Choose fewer or less expensive activities.",
                )
            if code == "23514" and message == "activity_budget_unavailable":
                raise HTTPException(
                    503,
                    "We couldn’t verify the group budget. "
                    "Try again before saving activities.",
                )
            if code == "P0001":
                raise HTTPException(
                    409, "This proposal changed. Reload before saving activities."
                )
            if code in {"23514", "22P02"}:
                raise HTTPException(422, "Select valid activities from this proposal.")
            raise HTTPException(
                503, "Activity storage is unavailable. Try again later."
            )
        preferences = name in {"rihla_get_preferences", "rihla_save_preferences"}
        if code in {"23514", "23502", "22001", "22003", "22007", "22008", "22P02"}:
            if name == "rihla_check_trip_dates":
                raise HTTPException(422, "Check the date values and date order.")
            if preferences:
                raise HTTPException(422, "Check the preference values and date order.")
            raise HTTPException(422, "Check the trip title and description.")
        if preferences:
            raise HTTPException(
                503,
                "Preference storage is unavailable. "
                "Check that the preferences migration is applied.",
            )
        if "proposal" in name or name == "rihla_get_group_conflicts":
            raise HTTPException(
                503,
                "Proposals are unavailable. "
                "Check that the proposals migrations are applied.",
            )
        if name in {"rihla_get_planning_status", "rihla_check_trip_dates"}:
            raise HTTPException(
                503,
                "Planning status is unavailable. "
                "Check that the readiness and planning overview migrations "
                "are applied.",
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
