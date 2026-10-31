"""Run the cheapest checks first, and generate only when they all pass.

Stage 1 is code only. Stage 2 is the feasibility answer in the first planning
request, so it adds no request. Stage 3 is the rest of generation.
Failure messages name a category only, never a member or a value.
"""

import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Protocol

from app.core.config import Settings
from app.schemas.generation import GenerationInput
from app.schemas.planning import ConflictCategory, PlanningStatus
from app.services.proposal_generation import (
    GenerationBlocked,
    GenerationResult,
    generate_proposals,
    load_demo_proposals,
)
from app.services.trip_research import ResearchCost

STOP_WORDS = {"or", "and", "the", "to", "in", "أو", "و", "في", "إلى"}
# Mirrored in SQL by rihla_private.destination_countries; a test keeps them equal.
# Stage 1 stops only when every word is a country from this list. Anything else,
# such as a city, is left for Gemini to judge in stage 2.
COUNTRY_WORDS = {
    "turkey": "turkey",
    "türkiye": "turkey",
    "turkiye": "turkey",
    "تركيا": "turkey",
    "egypt": "egypt",
    "مصر": "egypt",
    "jordan": "jordan",
    "الأردن": "jordan",
    "الاردن": "jordan",
    "georgia": "georgia",
    "جورجيا": "georgia",
    "azerbaijan": "azerbaijan",
    "أذربيجان": "azerbaijan",
    "اذربيجان": "azerbaijan",
    "oman": "oman",
    "عمان": "oman",
    "qatar": "qatar",
    "قطر": "qatar",
    "bahrain": "bahrain",
    "البحرين": "bahrain",
    "kuwait": "kuwait",
    "الكويت": "kuwait",
    "uae": "uae",
    "الإمارات": "uae",
    "الامارات": "uae",
    "lebanon": "lebanon",
    "لبنان": "lebanon",
    "morocco": "morocco",
    "المغرب": "morocco",
    "tunisia": "tunisia",
    "تونس": "tunisia",
    "malaysia": "malaysia",
    "ماليزيا": "malaysia",
    "thailand": "thailand",
    "تايلاند": "thailand",
    "indonesia": "indonesia",
    "إندونيسيا": "indonesia",
    "اندونيسيا": "indonesia",
    "japan": "japan",
    "اليابان": "japan",
    "italy": "italy",
    "إيطاليا": "italy",
    "ايطاليا": "italy",
    "france": "france",
    "فرنسا": "france",
    "spain": "spain",
    "إسبانيا": "spain",
    "اسبانيا": "spain",
    "greece": "greece",
    "اليونان": "greece",
    "germany": "germany",
    "ألمانيا": "germany",
    "المانيا": "germany",
}


class ProposalStore(Protocol):
    def load(self, trip_id: str, input_hash: str) -> GenerationResult | None: ...

    def save(self, trip_id: str, input_hash: str, result: GenerationResult) -> None: ...


class LocalProposalStore:
    """Local stand-in until the proposals table exists. Holds private flight data."""

    def __init__(self, path: Path, ttl_seconds: int) -> None:
        self.path = path
        self.ttl_seconds = ttl_seconds

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS generations "
            "(trip_id TEXT PRIMARY KEY, input_hash TEXT NOT NULL, "
            "saved_at REAL NOT NULL, result TEXT NOT NULL)"
        )
        return connection

    def load(self, trip_id: str, input_hash: str) -> GenerationResult | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT saved_at, result FROM generations "
                "WHERE trip_id = ? AND input_hash = ?",
                (trip_id, input_hash),
            ).fetchone()
        finally:
            connection.close()
        # Fares change, so old proposals are not reused after the time limit.
        if row is None or time.time() - row[0] >= self.ttl_seconds:
            return None
        return GenerationResult.model_validate_json(row[1])

    def save(self, trip_id: str, input_hash: str, result: GenerationResult) -> None:
        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    "INSERT OR REPLACE INTO generations VALUES (?, ?, ?, ?)",
                    (trip_id, input_hash, time.time(), result.model_dump_json()),
                )
        finally:
            connection.close()


def input_hash(generation: GenerationInput) -> str:
    """Stable across member order. Backend only: budgets are guessable from it."""
    members = sorted(
        json.dumps(
            member.model_dump(mode="json", exclude={"label"}),
            sort_keys=True,
            ensure_ascii=False,
        ).casefold()
        for member in generation.members
    )
    payload = json.dumps(
        [
            str(generation.trip_id),
            generation.shared_start.isoformat(),
            generation.shared_end.isoformat(),
            members,
        ]
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def find_planning_conflicts(planning: PlanningStatus) -> list[ConflictCategory]:
    conflicts: list[ConflictCategory] = []
    if not planning.all_members_ready:
        conflicts.append("readiness")
    if planning.shared_dates.status != "available":
        conflicts.append("dates")
    return conflicts


def check_planning(planning: PlanningStatus) -> None:
    conflicts = find_planning_conflicts(planning)
    if conflicts:
        raise GenerationBlocked(*conflicts)


def _known_countries(text: str) -> set[str] | None:
    """The countries named, or None if any word is not a known country."""
    words = set(re.findall(r"\w+", text.casefold())) - STOP_WORDS
    if not words or not words <= COUNTRY_WORDS.keys():
        return None
    return {COUNTRY_WORDS[word] for word in words}


def find_input_conflicts(
    generation: GenerationInput, settings: Settings
) -> list[ConflictCategory]:
    """Stage 1 checks on the group's data. Makes no outside request."""
    conflicts: list[ConflictCategory] = []
    wanted = [
        _known_countries(member.destinations.value)
        for member in generation.members
        if member.destinations.importance == "Essential" and member.destinations.value
    ]
    # A clear conflict only: any doubtful value goes to stage 2 instead.
    known = [item for item in wanted if item is not None]
    if len(known) == len(wanted) > 1 and not set.intersection(*known):
        conflicts.append("destinations")

    days = (generation.shared_end - generation.shared_start).days + 1
    lowest = min(member.max_budget_sar for member in generation.members)
    if lowest < settings.min_budget_sar_per_day * days:
        conflicts.append("budget")
    return conflicts


def check_input(generation: GenerationInput, settings: Settings) -> None:
    conflicts = find_input_conflicts(generation, settings)
    if conflicts:
        raise GenerationBlocked(*conflicts)


async def generate_checked(
    generation: GenerationInput,
    settings: Settings,
    store: ProposalStore | None = None,
    planning: PlanningStatus | None = None,
    version: int = 1,
    regenerate: bool = False,
) -> GenerationResult:
    """The entry point for generation. Raises GenerationBlocked when a check fails.

    regenerate skips saved proposals. The caller must allow it for the admin only.
    """
    if settings.proposals_demo_mode:
        return load_demo_proposals(generation, settings, version)

    if planning is not None:
        check_planning(planning)
    check_input(generation, settings)

    store = store or LocalProposalStore(
        settings.generation_store_db, settings.saved_proposals_ttl_hours * 3600
    )
    trip_id = str(generation.trip_id)
    current_hash = input_hash(generation)
    saved = None if regenerate else store.load(trip_id, current_hash)
    if saved is not None:
        return saved.model_copy(update={"reused": True, "cost": ResearchCost()})

    result = await generate_proposals(generation, settings, version)
    if result.complete:
        store.save(trip_id, current_hash, result)
    return result
