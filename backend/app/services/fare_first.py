"""Fare-first generation: only destinations with real, bookable flights are researched.

Why it exists. The old flow planned 3 trips one at a time, researched each with web
searches and Gemini, and only then looked for flights. A trip with no flights failed
after minutes of work, was retried, and the flight could fall back to a web number
with no booking link. Here:

  1. Gemini suggests several destinations in ONE request (dates inside the group's).
  2. Code checks them without any outside request (dates, privacy, requirements).
  3. Ignav is asked, for every departure city at the same time, whether each trip has
     a bookable round trip with a booking link. A day with none is retried a day or
     two later or earlier, inside the group's dates and never too soon to book.
  4. The first 3 trips with flights from every city are researched at the same time.
  5. If fewer than 3 have flights, Gemini is asked once more, told those routes had
     no flights. If none at all, the error says why and what the group can change.

A flight price is never shown without a booking link: research is told to stop if a
departure city with an airport has no live fare.
"""

import asyncio
import logging
from collections import Counter
from datetime import date, timedelta

from app.core.config import Settings
from app.schemas.generation import GenerationInput
from app.schemas.proposals import Proposal
from app.services.flight_prices import (
    FlightQuery,
    IgnavProvider,
    airport_for_city,
    get_flight_provider,
)
from app.services.generation_errors import no_flights_error, no_proposals_error
from app.services.generation_progress import ProgressReporter
from app.services.proposal_generation import (
    STOPPING_ERRORS,
    FailureReason,
    GenerationBlocked,
    GenerationResult,
    OptionFailure,
    OptionRejected,
    PlannedOption,
    _plan_options,
    _prevalidate,
    _research_option,
    _valid_airport,
    collect_requirements,
    route_key,
)
from app.services.trip_research import (
    ResearchCost,
    ResearchError,
    SearchCache,
    _fare_in_sar,
)

logger = logging.getLogger(__name__)

TARGET = 3


def live_fares_on(settings: Settings) -> bool:
    return settings.flight_price_provider == "ignav" and bool(settings.ignav_api_key)


def today() -> date:
    """Separate so tests can fix the date."""
    return date.today()


def candidate_starts(
    option: PlannedOption,
    generation: GenerationInput,
    earliest: date,
    shifts: list[int],
) -> list[date]:
    """The planned start first, then nearby days; every one keeps the trip length
    inside the group's dates and no sooner than the earliest bookable day."""
    length = option.end_date - option.start_date
    first = max(option.start_date, earliest)
    tries = [first, *(first + timedelta(days=shift) for shift in shifts)]
    lowest = max(generation.shared_start, earliest)
    found: list[date] = []
    for start in tries:
        if start >= lowest and start + length <= generation.shared_end:
            if start not in found:
                found.append(start)
    return found


def moved(option: PlannedOption, start: date) -> PlannedOption:
    length = option.end_date - option.start_date
    return option.model_copy(update={"start_date": start, "end_date": start + length})


async def probe_option(
    option: PlannedOption,
    generation: GenerationInput,
    provider: IgnavProvider,
    earliest: date,
    shifts: list[int],
) -> PlannedOption | None:
    """The option on the first day that has a bookable fare from every city."""
    arrival = _valid_airport(option.arrival_airport)
    if arrival is None:
        return None
    travelers = Counter(
        member.departure_city.strip().casefold() for member in generation.members
    )
    airports: dict[str, int] = {}
    for city, count in travelers.items():
        airport = airport_for_city(city)
        # A city without a known airport keeps the old web search, as before.
        if airport and airport != arrival:
            airports[airport] = airports.get(airport, 0) + count
    starts = candidate_starts(option, generation, earliest, shifts)
    if not airports:
        return moved(option, starts[0]) if starts else None
    length = option.end_date - option.start_date
    for start in starts:
        fares = await asyncio.gather(
            *(
                provider.find(
                    FlightQuery(origin, arrival, start, start + length, adults)
                )
                for origin, adults in airports.items()
            )
        )
        if all(fare is not None and _fare_in_sar(fare) is not None for fare in fares):
            return moved(option, start)
    return None


async def generate(
    generation: GenerationInput,
    settings: Settings,
    version: int,
    progress: ProgressReporter | None = None,
) -> GenerationResult:
    progress = progress or ProgressReporter(None)
    cost = ResearchCost()
    requirements = collect_requirements(generation)
    origins = list(
        {
            member.departure_city.casefold(): member.departure_city
            for member in generation.members
        }.values()
    )
    cache = SearchCache(
        settings.search_cache_db, settings.search_cache_ttl_hours * 3600
    )
    provider = get_flight_provider(settings, cache)
    if not isinstance(provider, IgnavProvider):  # pragma: no cover - guarded above
        raise ResearchError("not_configured", "Live fares are not set up.")
    earliest = today() + timedelta(days=settings.min_departure_lead_days)

    used: set[tuple[str, tuple[str, ...]]] = set()
    accepted: list[tuple[PlannedOption, list]] = []
    failures: list[FailureReason] = []
    no_flight_places: list[str] = []
    planned_nights: int | None = None

    progress.stage("planning")
    planned = await _plan_options(
        settings.planner_option_count,
        generation,
        requirements,
        used,
        settings,
        cost,
        first=True,
    )
    asked_again = False
    while True:
        valid: list[tuple[PlannedOption, list]] = []
        for option in planned:
            key = route_key(option.destination, [c.city for c in option.cities])
            if any(key[1] == known[1] for known in used):
                failures.append("duplicate_route")
                continue
            used.add(key)
            try:
                valid.append((option, _prevalidate(option, generation, requirements)))
            except OptionRejected as rejected:
                failures += rejected.reasons
                continue
            planned_nights = (option.end_date - option.start_date).days

        progress.stage("checking_flights")
        position = 0
        while len(accepted) < TARGET and position < len(valid):
            wave = valid[position : position + TARGET - len(accepted)]
            position += len(wave)
            for option, _ in wave:
                progress.option(
                    option_key(option),
                    title=option.title_en or option.title,
                    title_ar=option.title_ar,
                    destination=option.destination,
                    destination_ar=option.destination_ar,
                    start_date=option.start_date,
                    end_date=option.end_date,
                    status="checking_flights",
                )
            found = await asyncio.gather(
                *(
                    probe_option(
                        option,
                        generation,
                        provider,
                        earliest,
                        settings.flight_date_shifts,
                    )
                    for option, _ in wave
                )
            )
            for (option, adjustments), result in zip(wave, found, strict=True):
                if result is None:
                    failures.append("no_flights")
                    no_flight_places.append(option.destination)
                    progress.option(option_key(option), status="no_flights")
                    continue
                shift = (result.start_date - option.start_date).days
                progress.option(
                    option_key(option),
                    status="dates_moved" if shift else "flights_found",
                    start_date=result.start_date,
                    end_date=result.end_date,
                    date_shift_days=shift,
                )
                accepted.append((result, adjustments))

        needed = TARGET - len(accepted)
        # One more Gemini request, and only when the limit still allows it.
        if (
            needed <= 0
            or asked_again
            or cost.gemini_requests + 1 > settings.max_gemini_calls_per_generation
        ):
            break
        asked_again = True
        progress.stage("planning")
        try:
            planned = await _plan_options(
                needed + 1,
                generation,
                requirements,
                used,
                settings,
                cost,
                previous_problem="no_flights" if no_flight_places else None,
            )
        except ResearchError as error:
            if error.code in STOPPING_ERRORS and not accepted:
                raise
            break
        if not planned:
            break

    cost.ignav_requests += provider.requests_made
    if not accepted:
        if "over_group_budget" in failures and "no_flights" not in failures:
            raise GenerationBlocked("budget")
        if no_flight_places:
            raise no_flights_error(
                generation,
                no_flight_places,
                today(),
                settings.min_departure_lead_days,
                planned_nights,
            )
        raise no_proposals_error()

    progress.stage("researching")
    for option, _ in accepted:
        progress.option(option_key(option), status="researching")

    async def research_one(number: int, option: PlannedOption, adjustments: list):
        try:
            proposal = await _research_option(
                option,
                number,
                generation,
                requirements,
                adjustments,
                origins,
                version,
                settings,
                cost,
                require_live_fares=True,
            )
        except OptionRejected:
            progress.option(option_key(option), status="failed")
            raise
        except ResearchError:
            progress.option(option_key(option), status="failed")
            raise
        hotel = proposal.cities[0] if proposal.cities else None
        progress.option(
            option_key(option),
            status="ready",
            hotel_name=hotel.hotel_name.value if hotel else None,
            hotel_price_per_night_sar=(
                hotel.hotel_price_per_night.amount_sar if hotel else None
            ),
            hotel_source=hotel.hotel_source if hotel else None,
        )
        return proposal

    outcomes = await asyncio.gather(
        *(
            research_one(number, option, adjustments)
            for number, (option, adjustments) in enumerate(accepted, start=1)
        ),
        return_exceptions=True,
    )
    proposals: list[Proposal] = []
    stopped: ResearchError | None = None
    option_failures: list[OptionFailure] = []
    for number, outcome in enumerate(outcomes, start=1):
        if isinstance(outcome, Proposal):
            proposals.append(outcome)
            continue
        reasons: list[FailureReason] = []
        if isinstance(outcome, OptionRejected):
            reasons = list(outcome.reasons)
        elif isinstance(outcome, ResearchError):
            if outcome.code in STOPPING_ERRORS:
                stopped = outcome
            reasons = [
                "no_flights" if outcome.code == "no_flights" else "research_failed"
            ]
        else:  # an unexpected bug in one option must not lose the others
            logger.exception("generation_option_crashed", exc_info=outcome)
            reasons = ["research_failed"]
        logger.info(
            "generation_option_failed option=%s reasons=%s", number, ",".join(reasons)
        )
        option_failures.append(OptionFailure(option_number=number, reasons=reasons))

    # Numbers follow the order shown, with no gaps.
    proposals = [
        proposal.model_copy(update={"option_number": index})
        for index, proposal in enumerate(proposals, start=1)
    ]
    if not proposals:
        if stopped is not None:
            raise stopped
        if all("over_group_budget" in item.reasons for item in option_failures):
            raise GenerationBlocked("budget")
        raise no_proposals_error()
    complete = len(proposals) == TARGET
    message = None
    if not complete:
        message = (
            f"Only {len(proposals)} of 3 proposals had bookable flights "
            "and passed the checks."
        )
    progress.stage("saving")
    return GenerationResult(
        proposals=proposals,
        complete=complete,
        message=message,
        failures=option_failures,
        cost=cost,
    )


def option_key(option: PlannedOption) -> str:
    parts = [option.destination, *(city.city for city in option.cities)]
    return "|".join(parts).casefold()
