"""Spike: one real generation for a fictional group. Spends Gemini and Tavily quota.

Run from the backend folder, with an output path outside the repository:
    uv run python spikes/generate_real_example.py <output.json>
"""

import asyncio
import logging
import sys
from datetime import date
from pathlib import Path
from uuid import UUID

from app.core.config import Settings
from app.schemas.generation import GenerationInput
from app.services.proposal_generation import generate_proposals
from app.services.trip_research import ResearchError

EXAMPLE = GenerationInput(
    trip_id=UUID("00000000-0000-4000-8000-0000000000dd"),
    shared_start=date(2026, 12, 13),
    shared_end=date(2026, 12, 17),
    members=[
        {"label": "Member 1", "departure_city": "Riyadh", "max_budget_sar": "4000"},
        {"label": "Member 2", "departure_city": "Riyadh", "max_budget_sar": "4000"},
    ],
)


async def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("app.services").setLevel(logging.INFO)
    try:
        result = await generate_proposals(EXAMPLE, Settings())
    except ResearchError as error:
        sys.exit(f"[{error.code}] {error.message}")
    Path(sys.argv[1]).write_text(result.model_dump_json(indent=2), encoding="utf-8")
    print("complete:", result.complete, "| message:", result.message)
    print("failures:", [item.model_dump() for item in result.failures])
    print("cost:", result.cost.model_dump())


asyncio.run(main())
