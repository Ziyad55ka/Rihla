"""Live progress of one trip's generation, so the page can show each step.

Held in memory for the running process only: a second backend worker would not see
it, which is fine for this project's single uvicorn process. It never holds private
data: no budgets, member cities or per-person flight prices. Titles have already
passed the privacy check, and a hotel's price per night is the same for everyone.
"""

import time
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

Stage = Literal[
    "planning", "checking_flights", "researching", "saving", "done", "failed"
]
OptionStatus = Literal[
    "checking_flights",
    "flights_found",
    "dates_moved",
    "no_flights",
    "researching",
    "ready",
    "failed",
]

# A finished entry stays this long, so a page that polls late still sees the end.
KEEP_SECONDS = 15 * 60


class OptionProgress(BaseModel):
    key: str
    title: str | None = None
    title_ar: str | None = None
    destination: str | None = None
    destination_ar: str | None = None
    status: OptionStatus = "checking_flights"
    start_date: date | None = None
    end_date: date | None = None
    # Days the departure moved to find flights (+ later, - earlier).
    date_shift_days: int = 0
    hotel_name: str | None = None
    hotel_price_per_night_sar: Decimal | None = None
    hotel_source: str | None = None


class GenerationProgress(BaseModel):
    stage: Stage = "planning"
    started_at: datetime
    updated_at: datetime
    options: list[OptionProgress] = []
    # How many proposals are needed and how many are ready.
    target: int = 3
    ready: int = 0


_progress: dict[str, tuple[float, GenerationProgress]] = {}


def _now() -> datetime:
    return datetime.now(UTC)


def _prune() -> None:
    limit = time.monotonic() - KEEP_SECONDS
    for key in [key for key, (seen, _) in _progress.items() if seen < limit]:
        _progress.pop(key, None)


class ProgressReporter:
    """Updates one trip's entry. Every method is safe to call when tracking is off."""

    def __init__(self, trip_id: str | None) -> None:
        self.trip_id = trip_id
        if trip_id is not None:
            _prune()
            now = _now()
            _progress[trip_id] = (
                time.monotonic(),
                GenerationProgress(started_at=now, updated_at=now),
            )

    def _entry(self) -> GenerationProgress | None:
        if self.trip_id is None or self.trip_id not in _progress:
            return None
        return _progress[self.trip_id][1]

    def _touch(self, entry: GenerationProgress) -> None:
        entry.updated_at = _now()
        entry.ready = sum(item.status == "ready" for item in entry.options)
        _progress[self.trip_id] = (time.monotonic(), entry)  # type: ignore[index]

    def stage(self, stage: Stage) -> None:
        if entry := self._entry():
            entry.stage = stage
            self._touch(entry)

    def option(self, key: str, **values) -> None:
        entry = self._entry()
        if entry is None:
            return
        for item in entry.options:
            if item.key == key:
                for name, value in values.items():
                    setattr(item, name, value)
                break
        else:
            entry.options.append(OptionProgress(key=key, **values))
        self._touch(entry)


def read_progress(trip_id: str) -> GenerationProgress | None:
    _prune()
    found = _progress.get(trip_id)
    return found[1] if found else None
