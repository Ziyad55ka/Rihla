# ruff: noqa: E501  (report strings read better unbroken)
"""Live accuracy check: real searches, checked against independent sources.

Run from `backend` (it spends real requests, so it is never part of pytest):

    uv run python -m scripts.live_accuracy                 # the daily set
    uv run python -m scripts.live_accuracy --only RUH-JED  # one route
    uv run python -m scripts.live_accuracy --no-activities
    uv run python -m scripts.live_accuracy --set weekly        # 15 routes, ~45 searches

Each route runs the same flight search generation uses (Ignav, with the Google
Flights check), then checks the result against what a member would meet:

  one_booking   outbound and return on ONE booking link, both https
  link          the airline link carries these airports, dates and passengers
  timing        dates inside the trip, return lands by the last day
  late_return   warns when the flight home leaves between 00:00 and 04:59
  pinned_page   the Google Flights page opens these exact flights for the group
  price         the airline's own round-trip total for the group on Google's
                booking page (sellers asked live), against Rihla's price
  extras        bags: what the fare includes and what Google lists as extra

Requests per route: 2 Google Flights searches (the check generation already
does) and 1 more for the booking page. Activities use Tavily and the model only.

The report goes to backend/.local/accuracy/<date>.md and .json. Scenarios are in
scripts/live_scenarios.json, with dates relative to today so they never expire.
"""

import argparse
import asyncio
import json
import logging
import re
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.core.config import Settings  # noqa: E402
from app.schemas.proposals import Flights, InfoField, SarPrice  # noqa: E402
from app.services.flight_prices import (  # noqa: E402
    FlightFare,
    FlightQuery,
    get_flight_provider,
)
from app.services.google_flights_check import _matches, _options  # noqa: E402
from app.services.google_flights_link import itinerary_url  # noqa: E402
from app.services.proposal_generation import _fare_leg  # noqa: E402

SCENARIOS = Path(__file__).with_name("live_scenarios.json")
NONE = InfoField(value=None, status="Not available", evidence=[])
NO_PRICE = SarPrice(amount_sar=None, status="Not available", evidence=[])
# A gap the member would notice at checkout. Under PASS is treated as the same price.
PASS_PERCENT = Decimal(2)
WARN_PERCENT = Decimal(5)


@dataclass
class Check:
    name: str
    status: str  # PASS, WARN, FAIL, INFO, SKIP
    detail: str


@dataclass
class RouteResult:
    route: str
    adults: int
    dates: str
    airline: str | None = None
    flights: str | None = None
    price_per_person: str | None = None
    price_status: str | None = None
    reason_none: str | None = None
    checks: list[Check] = field(default_factory=list)
    links: dict = field(default_factory=dict)

    def worst(self) -> str:
        order = ["FAIL", "WARN", "PASS", "INFO", "SKIP"]
        found = [item.status for item in self.checks] or ["SKIP"]
        return min(found, key=order.index)


class Reasons(logging.Handler):
    """Collects the log lines that explain why no fare came back."""

    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        text = record.getMessage()
        if any(key in text for key in ("fallback", "not_listed", "failed")):
            self.lines.append(text)


# ---------------------------------------------------------------- link checks
def unwrap(url: str) -> str:
    for _ in range(3):
        query = parse_qs(urlparse(url).query)
        inner = next(
            (
                values[0]
                for key, values in query.items()
                if key.lower() in ("url", "u", "redirect", "dest")
                and values[0].startswith("http")
            ),
            None,
        )
        if not inner:
            break
        url = inner
    return url


def date_forms(day: date) -> set[str]:
    y, m, d = f"{day.year:04d}", f"{day.month:02d}", f"{day.day:02d}"
    return {
        f"{y}-{m}-{d}",
        f"{m}/{d}/{y}",
        f"{d}/{m}/{y}",
        f"{d}{m}{y[2:]}",
        f"{y}{m}{d}",
    }


def link_problems(url: str, query: FlightQuery) -> list[str]:
    text = unquote(unquote(unwrap(url)))
    problems = []
    for code in (query.origin_airport, query.destination_airport):
        if code not in text:
            problems.append(f"{code} missing")
    if not any(form in text for form in date_forms(query.departure_date)):
        problems.append("outbound date missing")
    if not any(form in text for form in date_forms(query.return_date)):
        problems.append("return date missing (not one round-trip link)")
    if re.search(r"(trip_?type|flightMode)=(O|OW|oneway|one_way)\b", text, re.I):
        problems.append("link says one-way")
    counts = re.findall(r"(?:adt1?|adults?|adultCount|pas=A:)[=:]?(\d+)", text, re.I)
    typed = len(re.findall(r"TRAVELLER_TYPE_\d+=ADT", text))
    found = int(counts[0]) if counts else (typed or None)
    if found is None:
        problems.append("passenger count not in link")
    elif found != query.adults:
        problems.append(f"link has {found} adults, group has {query.adults}")
    return problems


# ------------------------------------------------------------- route checks
def as_route(fare: FlightFare, query: FlightQuery) -> Flights:
    return Flights(
        origin=query.origin_airport,
        trip_type=fare.trip_type,
        legs=[_fare_leg(leg, []) for leg in fare.legs],
        airline=NONE,
        duration=NONE,
        price_per_person=NO_PRICE,
        origin_airport=query.origin_airport,
        destination_airport=query.destination_airport,
    )


def booking_page(verifier, query: FlightQuery, fare: FlightFare):
    """The return option Google listed for these flights, from the check's cache."""
    numbers = {
        leg.direction: tuple(
            part.replace(" ", "") for part in (leg.flight_number or "").split(",")
        )
        for leg in fare.legs
    }
    for key, body in verifier._seen.items():
        if '"departure_token"' not in key or not body:
            continue
        for option in _options(body):
            if _matches(option, numbers.get("return", ()), query, True):
                return option
    return None


async def check_price(verifier, query, fare, result: RouteResult) -> None:
    option = booking_page(verifier, query, fare)
    if option is None or not option.get("booking_token"):
        result.checks.append(
            Check("price", "SKIP", "Google listed no booking page for these flights")
        )
        return
    page = await verifier._get(
        {**verifier._params(query), "booking_token": option["booking_token"]}
    )
    if not page:
        result.checks.append(Check("price", "SKIP", "Google booking page unreachable"))
        return
    sellers = []
    for item in page.get("booking_options") or []:
        together = item.get("together") or {}
        if together.get("price"):
            sellers.append(
                (
                    together.get("book_with"),
                    bool(together.get("airline")),
                    together["price"],
                )
            )
    ours = Decimal(fare.amount)
    airline = next((s for s in sellers if s[1]), None)
    cheapest = min(sellers, key=lambda s: s[2]) if sellers else None
    if airline is None:
        result.checks.append(
            Check(
                "price",
                "WARN" if fare.price_source == "seller" else "INFO",
                f"Google hides the airline's own price. Rihla {ours} pp ({fare.price_source});"
                + (
                    f" lowest seller {cheapest[0]} {Decimal(cheapest[2]) / query.adults:.2f} pp"
                    if cheapest
                    else ""
                ),
            )
        )
    else:
        theirs = Decimal(airline[2]) / query.adults
        gap = (ours - theirs) / theirs * 100
        status = (
            "PASS"
            if abs(gap) <= PASS_PERCENT
            else "WARN"
            if abs(gap) <= WARN_PERCENT
            else "FAIL"
        )
        result.checks.append(
            Check(
                "price",
                status,
                f"Rihla {ours} pp vs {airline[0]} (airline) {theirs:.2f} pp on Google's "
                f"booking page, gap {gap:+.1f}%",
            )
        )
    if cheapest and airline and cheapest[2] < airline[2] * Decimal("0.95"):
        result.checks.append(
            Check(
                "agent",
                "INFO",
                f"{cheapest[0]} sells the same flights for {Decimal(cheapest[2]) / query.adults:.2f} pp",
            )
        )
    bags = page.get("baggage_prices") or {}
    lines = []
    for direction in ("together", "departing", "returning"):
        for text in (
            bags.get(direction, []) if isinstance(bags.get(direction), list) else []
        ):
            lines.append(str(text))
    extensions = sorted(
        {
            str(text)
            for flight in option.get("flights") or []
            for text in flight.get("extensions") or []
            if "bag" in str(text).lower()
        }
    )
    included = fare.checked_bags
    if lines or extensions:
        result.checks.append(
            Check(
                "extras",
                # Unknown bags are not an error: the page tells the group to check.
                "INFO",
                f"Rihla checked bags={included}; Google: {'; '.join(lines + extensions)[:300]}"
                + ("" if included is not None else " (page shows the extra-fees note)"),
            )
        )
    else:
        result.checks.append(
            Check(
                "extras", "INFO", "No bag information; page shows the extra-fees note"
            )
        )


async def run_route(item: dict, settings: Settings, today: date) -> RouteResult:
    start = today + timedelta(days=item["days_ahead"])
    end = start + timedelta(days=item["nights"])
    origin, destination = item["route"].split("-")
    query = FlightQuery(origin, destination, start, end, item["adults"])
    result = RouteResult(item["route"], item["adults"], f"{start} to {end}")
    provider = get_flight_provider(settings, verify=True)
    reasons = Reasons()
    logging.getLogger("app").addHandler(reasons)
    try:
        fare = await provider.find(query)
    finally:
        logging.getLogger("app").removeHandler(reasons)
    if fare is None:
        named = getattr(provider, "miss_reasons", {}).get(query)
        result.reason_none = named or "; ".join(reasons.lines) or "no reason logged"
        expected = item.get("expect") == "none"
        result.checks.append(
            Check(
                "found",
                "PASS" if expected else "FAIL",
                f"No bookable round trip. Reason given: {result.reason_none}",
            )
        )
        # The group is told why, in plain words, rather than "try later".
        result.checks.append(
            Check(
                "reason_named",
                "PASS" if named else "FAIL",
                f"reason for the group: {named}" if named else "no plain reason",
            )
        )
        return result
    out, back = fare.legs[0], fare.legs[-1]
    result.airline = fare.airline
    result.flights = f"{out.flight_number} / {back.flight_number}"
    result.price_per_person = fare.amount
    result.price_status = f"{fare.price_source}, verified={fare.verified}"

    same = (
        len(fare.legs) == 2 and out.booking_url and out.booking_url == back.booking_url
    )
    result.checks.append(
        Check(
            "one_booking",
            "PASS" if fare.trip_type == "round_trip" and same else "FAIL",
            f"trip_type={fare.trip_type}, one link for both={bool(same)}",
        )
    )
    if out.booking_url:
        result.links["airline"] = out.booking_url
        problems = link_problems(out.booking_url, query)
        result.checks.append(
            Check(
                "link",
                "PASS" if not problems else "FAIL",
                f"{urlparse(unwrap(out.booking_url)).netloc}"
                + (
                    f": {', '.join(problems)}"
                    if problems
                    else ", exact flight"
                    if fare.exact
                    else ", results page"
                ),
            )
        )
    timing = []
    if out.date != start.isoformat():
        timing.append(f"outbound on {out.date}, asked {start}")
    if back.date != end.isoformat():
        timing.append(f"return on {back.date}, asked {end}")
    if back.arrival_time and back.arrival_time[:10] > end.isoformat():
        timing.append(f"return lands {back.arrival_time}, after the last day")
    result.checks.append(
        Check(
            "timing",
            "FAIL" if timing else "PASS",
            "; ".join(timing) or f"{out.departure_time} / {back.departure_time}",
        )
    )
    hour = int(back.departure_time[11:13]) if back.departure_time else None
    if hour is not None and hour < 5:
        result.checks.append(
            Check(
                "late_return",
                "INFO",
                f"Home flight leaves {back.departure_time}: the last hotel night is "
                f"not counted or booked, and the page says why",
            )
        )
    pinned = itinerary_url(as_route(fare, query), query.adults)
    result.links["pinned"] = pinned
    result.checks.append(
        Check(
            "pinned_page",
            "PASS" if pinned else "FAIL",
            "both flights selected for the group"
            if pinned
            else "a segment detail is missing",
        )
    )
    if provider.verifier is not None:
        await check_price(provider.verifier, query, fare, result)
    else:
        result.checks.append(Check("price", "SKIP", "Google Flights check is off"))
    return result


# --------------------------------------------------------------- activities
async def run_activities(settings: Settings, today: date) -> dict:
    from app.schemas.proposals import Proposal
    from app.services.activity_research import find_activities
    from app.services.trip_research import SearchCache

    raw = json.loads((BACKEND / "app/data/demo_proposals.json").read_text())[
        "proposals"
    ][0]
    start = today + timedelta(days=30)
    nights = sum(city["nights"] for city in raw["cities"])
    raw = {
        **raw,
        "id": str(uuid.uuid4()),
        "start_date": start.isoformat(),
        "end_date": (start + timedelta(days=nights)).isoformat(),
    }
    proposal = await find_activities(Proposal.model_validate(raw), settings)
    cache = SearchCache(settings.search_cache_db, 10**9)
    import sqlite3

    pages = []
    with sqlite3.connect(cache.path) as connection:
        for (results,) in connection.execute("SELECT results FROM searches"):
            for item in json.loads(results):
                text = " ".join(
                    str(item.get(k) or "") for k in ("title", "content", "raw_content")
                )
                pages.append((item.get("url"), re.sub(r"\W+", " ", text).lower()))
    sources = {source.id: source.url for source in proposal.sources}
    checked = missing = unpriced = 0
    problems = []
    names = []
    for stay in proposal.cities:
        for activity in stay.activities:
            names.append(
                f"{activity.name.value} ({activity.category}, "
                f"{activity.price_per_person.amount_sar} SAR {activity.price_per_person.status})"
            )
            if activity.price_per_person.status in ("Unconfirmed", "Not available"):
                unpriced += 1
            fields = [
                activity.name,
                activity.description,
                activity.location,
                activity.duration,
            ]
            evidence = [e for f in fields for e in f.evidence] + list(
                activity.price_per_person.evidence
            )
            for item in evidence:
                checked += 1
                quote = re.sub(r"\W+", " ", item.quote).lower().strip()
                url = sources.get(item.source_id)
                if not any(
                    quote in text for page_url, text in pages if page_url == url
                ):
                    missing += 1
                    problems.append(f"'{item.quote[:60]}' not in {url}")
    return {
        "city": proposal.destination,
        "status": proposal.activity_research_status,
        "activities": len(names),
        "quotes_checked": checked,
        "quotes_missing": missing,
        "price_unconfirmed": unpriced,
        "problems": problems[:10],
        "list": names,
    }


# ------------------------------------------------------------------ report
def write_report(
    results: list[RouteResult], activities: dict | None, out: Path, spent: int
) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d_%H%M")
    lines = [f"# Rihla live accuracy, {time.strftime('%Y-%m-%d %H:%M')}", ""]
    totals: dict[str, int] = {}
    for result in results:
        for check in result.checks:
            totals[check.status] = totals.get(check.status, 0) + 1
    lines.append("Checks: " + ", ".join(f"{k} {v}" for k, v in sorted(totals.items())))
    lines.append(f"Google Flights requests: {spent}")
    airlines: dict[str, int] = {}
    for result in results:
        if result.airline:
            airlines[result.airline] = airlines.get(result.airline, 0) + 1
    lines.append(
        "Airlines chosen: "
        + (", ".join(f"{name} x{count}" for name, count in airlines.items()) or "none")
    )
    lines.append("")
    lines.append("| Route | Pax | Airline | Flights | Rihla pp | Result |")
    lines.append("|---|---|---|---|---|---|")
    for r in results:
        lines.append(
            f"| {r.route} | {r.adults} | {r.airline or '-'} | {r.flights or '-'} | {r.price_per_person or '-'} | {r.worst()} |"
        )
    for r in results:
        lines += ["", f"## {r.route} ({r.dates}, {r.adults} adults)"]
        for c in r.checks:
            lines.append(f"- **{c.status}** {c.name}: {c.detail}")
        for name, url in r.links.items():
            if url:
                lines.append(f"- {name} link: {url}")
    if activities:
        lines += [
            "",
            f"## Activities: {activities['city']}",
            f"- status {activities['status']}, {activities['activities']} found",
            f"- quotes checked {activities['quotes_checked']}, missing from their source {activities['quotes_missing']}",
            f"- prices only estimated by the model: {activities['price_unconfirmed']}",
        ]
        lines += [f"- {p}" for p in activities["problems"]]
    path = out / f"{stamp}.md"
    path.write_text("\n".join(lines) + "\n")
    (out / f"{stamp}.json").write_text(
        json.dumps(
            {"routes": [asdict(r) for r in results], "activities": activities},
            indent=1,
            ensure_ascii=False,
        )
    )
    return path


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", help="Routes to run, comma separated, e.g. RUH-JED")
    parser.add_argument(
        "--set", default="daily", help="Scenario set in live_scenarios.json"
    )
    parser.add_argument("--no-activities", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    logging.getLogger("app").setLevel(logging.INFO)
    settings = Settings()
    scenarios = json.loads(SCENARIOS.read_text())[args.set]
    if args.only:
        wanted = set(args.only.split(","))
        scenarios = [s for s in scenarios if s["route"] in wanted]
    today = date.today()
    results = []
    from app.services import google_flights_check

    spent = 0
    original = google_flights_check.GoogleFlightsCheck._get

    async def counted(self, params):
        nonlocal spent
        before = self.requests_made
        body = await original(self, params)
        spent += self.requests_made - before
        return body

    google_flights_check.GoogleFlightsCheck._get = counted
    for item in scenarios:
        print(f"... {item['route']} ({item['adults']} adults)", flush=True)
        try:
            # A stuck source must not stop the run, and is itself a finding.
            results.append(
                await asyncio.wait_for(run_route(item, settings, today), timeout=150)
            )
        except Exception as error:  # A crash is a result too.
            failed = RouteResult(item["route"], item["adults"], "")
            failed.checks.append(
                Check("run", "FAIL", f"{type(error).__name__}: {error}")
            )
            results.append(failed)
        print(
            f"    {results[-1].worst()}  {results[-1].airline or ''} {results[-1].flights or ''}",
            flush=True,
        )
        # Saved after every route, so a stopped run keeps what it already paid for.
        partial = settings.flight_usage_db.parent / "accuracy" / "partial.json"
        partial.parent.mkdir(parents=True, exist_ok=True)
        partial.write_text(
            json.dumps([asdict(r) for r in results], indent=1, ensure_ascii=False)
        )
    activities = None
    if not args.no_activities:
        print("... activities", flush=True)
        activities = await run_activities(settings, today)
    path = write_report(
        results, activities, settings.flight_usage_db.parent / "accuracy", spent
    )
    print(f"\nReport: {path}")


if __name__ == "__main__":
    asyncio.run(main())
