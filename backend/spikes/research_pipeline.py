"""Spike: run search -> Gemini -> verified fields once, using fictional inputs only.

Run from the backend folder:
    uv run python spikes/research_pipeline.py

Costs 1 Gemini request and 1 Tavily credit per uncached search (2 for this example).
"""

import asyncio
import logging
import sys

from app.core.config import Settings
from app.services.trip_research import ResearchError, ResearchRequest, research

REQUEST = ResearchRequest(
    destination="Istanbul",
    cities=["Istanbul"],
    period="late November",
    origins=["Riyadh"],
)


async def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("app.services.trip_research").setLevel(logging.INFO)
    try:
        result = await research(REQUEST, Settings())
    except ResearchError as error:
        sys.exit(f"[{error.code}] {error.message}")
    print(
        result.model_dump_json(indent=2, exclude={"sources": {"__all__": {"content"}}})
    )


asyncio.run(main())
