"""Whole-generation scenarios with deterministic supplier/model doubles."""

import asyncio
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core.config import Settings
from app.schemas.generation import GenerationInput
from app.services import proposal_generation, trip_research
from app.services.proposal_costs import proposal_costs
from tests.proposals.test_proposal_generation import fake_planner, fake_research, option


@pytest.mark.parametrize("members", [1, 3, 8])
@pytest.mark.parametrize(
    "start,nights,night_price",
    [
        (date(2027, 1, 10), 1, "200"),
        (date(2028, 2, 28), 4, "450"),
        (date(2027, 12, 28), 7, "900"),
    ],
)
def test_generation_costs_stay_consistent_for_group_sizes_and_calendar_boundaries(
    tmp_path, monkeypatch, members, start, nights, night_price
):
    end = start + timedelta(days=nights)
    data = GenerationInput(
        trip_id="00000000-0000-4000-8000-000000000077",
        shared_start=start,
        shared_end=end,
        members=[
            {
                "label": f"Member {i + 1}",
                "departure_city": ["Riyadh", "Jeddah"][i % 2],
                "max_budget_sar": "25000",
            }
            for i in range(members)
        ],
    )
    plans = [
        option(city).model_copy(
            update={
                "start_date": start,
                "end_date": end,
                "cities": [proposal_generation.PlannedCity(city=city, nights=nights)],
            }
        )
        for city in ["Cairo", "Doha", "Istanbul"]
    ]
    payloads = fake_planner(monkeypatch, plans)
    monkeypatch.setattr(trip_research, "research", fake_research(night=night_price))
    settings = Settings(
        _env_file=None,
        ignav_api_key=None,
        gemini_api_key="fake",
        tavily_api_key="fake",
        search_cache_db=tmp_path / "cache.sqlite3",
    )
    result = asyncio.run(proposal_generation.generate_proposals(data, settings))
    assert result.complete and len(result.proposals) == 3
    assert len(payloads) == 1
    expected = (
        Decimal("1000") + Decimal(night_price) * nights + Decimal("225") * (nights + 1)
    )
    for proposal in result.proposals:
        assert proposal.start_date == start and proposal.end_date == end
        assert sum(city.nights for city in proposal.cities) == nights
        assert len(proposal.flights) == min(members, 2)
        costs = proposal_costs(proposal, Decimal(150), None)
        assert costs.scenarios[0].per_person_total.amount_sar == expected
        assert expected < Decimal("25000")
