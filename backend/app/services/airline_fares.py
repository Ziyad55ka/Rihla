"""General facts about each airline's cheapest fare, from app/data/airline_fares.json."""

import json
from functools import lru_cache
from pathlib import Path

from app.schemas.proposals import AirlineFareNote, Flights

FARES_FILE = Path(__file__).resolve().parents[1] / "data" / "airline_fares.json"


@lru_cache
def _table() -> dict[str, AirlineFareNote]:
    raw = json.loads(FARES_FILE.read_text(encoding="utf-8"))
    return {
        code: AirlineFareNote(
            code=code,
            name_en=item["name_en"],
            name_ar=item["name_ar"],
            fare_en=item["fare_en"],
            fare_ar=item["fare_ar"],
            checked_kg=item["checked_kg"],
        )
        for code, item in raw.items()
        if not code.startswith("_")
    }


def fare_notes(route: Flights) -> list[AirlineFareNote]:
    """One note per airline flown, found from its flight numbers, in flight order."""
    table = _table()
    codes: list[str] = []
    for leg in route.legs:
        code = (leg.flight_number or "").split(" ")[0].upper()
        if code in table and code not in codes:
            codes.append(code)
    return [table[code] for code in codes]
