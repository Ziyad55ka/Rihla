# AI proposals (US-09)

How Rihla generates three trip proposals, and what the results can and cannot be trusted for. There is no API route or database storage yet: generation currently runs from `backend/spikes/generate_real_example.py` or in demo mode.

## Checks before generation

`generate_checked` in `backend/app/services/generation_precheck.py` is the entry point. It runs the cheapest checks first.

| Stage | Cost | Checks | On failure |
| --- | --- | --- | --- |
| 1 | No outside request | All members Ready, shared dates exist, Essential destinations overlap, lowest budget is at least `MIN_BUDGET_SAR_PER_DAY` per trip day, and whether the inputs changed | Stops. Unchanged inputs return the saved proposals |
| 2 | 1 Gemini request | Whether Essential requirements, the lowest budget and the dates can fit together | Stops. When unsure, Gemini is told to allow it |
| 3 | Full generation | See below | See below |

Failures raise `GenerationBlocked`, with messages by category only: `readiness`, `dates`, `destinations`, `flights`, `accommodation` or `budget`. They never name a member or a value, and Gemini's words are not shown. If every proposal fails on budget, the result is a `budget` message without the figure.

The inputs hash covers the trip, dates and every member's data, ignoring member order. It can be guessed from budgets, so it stays in the backend. Until the proposals table exists, results are stored in `backend/.local/generations.sqlite3`. Only complete results are saved for reuse.

Demo mode skips these checks. Flights use the cheapest itinerary even when it needs two bookings.

## How generation works

Code: `backend/app/services/proposal_generation.py`, `trip_research.py`, `flight_prices.py`.

1. **Input.** `schemas/generation.py` defines anonymous members (`Member 1`, `Member 2`) with departure city, budget and preferences. The planned private RPC must return this shape.
2. **Plan.** Gemini proposes three different routes from group-level data only: the lowest budget, shared dates and an unattributed list of requirements.
3. **Flights.** `FlightPriceProvider` asks Ignav for a round-trip fare per departure city. If Ignav has no key, fails or finds nothing, that city falls back to the web search.
4. **Hotels and transfers.** Tavily basic searches name the city and country. Sources that clearly describe another country are dropped. Gemini extracts facts and quotes from the results.
5. **Verification.** Code checks each quote against its source and applies the price policy below.
6. **Checks.** Each proposal is checked for full cost per person, shared dates, Essential and Flexible requirements, a distinct route and private details in its text.
7. **Retries.** A failed proposal is regenerated at most twice. If some still fail, the others are returned with a clear message. A Gemini quota limit or outage gets one delayed retry, then generation stops.

`PROPOSALS_DEMO_MODE=true` serves `backend/app/data/demo_proposals.json` with no external calls, and marks the result as demo.

## Privacy decisions

- Budgets and preferences stay in the backend. They never appear in a proposal.
- The planner receives no member labels or departure cities. It does receive the lowest budget and the preference text.
- Departure cities are sent to Ignav or Tavily, and to Gemini during extraction, without member identity.
- Titles and explanations are rejected if they contain a member's budget figure or departure city. Explanations also reject any digit.
- A stored proposal holds flights from every departure city. Browser responses must pass through `view_for_member`, which also removes sources no longer cited. See [the flight visibility decision](sprint-1-decisions.md).
- Logs hold only categories and reasons, never values, queries or cities.

## Price policy

| Situation | Result | Evidence |
| --- | --- | --- |
| Verified Ignav `round_trip` fare in SAR | `Sourced` (flights only) | Booking link |
| Ignav `split` or `one_way` fare, or any other Ignav fare | `Estimated` | Booking link |
| Web price in SAR | `Estimated` | Quote |
| Web price in another currency, a range or "starting from" | `Estimated`, converted to SAR; a range uses its upper bound | Quote |
| No usable price in the sources | `Unconfirmed`, Gemini's general estimate | None |
| No price at all | `Not available` | None |

Conversion uses the fixed table `SAR_PER_UNIT` in `trip_research.py`, last updated 2026-11-01. Review it before presenting results. The original price and currency are kept only in the internal research result.

Full cost per person is the costliest departure city's fare, plus every hotel night with no room sharing, plus transfers.

| `budget_status` | Meaning |
| --- | --- |
| `within_group_budget` | Total is within the lowest budget, and all prices are `Sourced` or `Estimated` |
| `includes_unconfirmed` | Known total is within the lowest budget, but a price is `Unconfirmed` or `Not available` |
| `over_group_budget` | Total exceeds the lowest budget. The proposal is rejected and regenerated, so it is not returned |

## Data sources

| Source | Used for | Free limit seen on 1 November 2026 |
| --- | --- | --- |
| Gemini (`gemini-3-flash-preview`) | Planning, extraction, general price estimates | 20 requests a day, 5 a minute |
| Tavily basic search | Hotels, transfers, flight fallback | 1,000 credits a month, 1 per search |
| Ignav | Round-trip fares and booking links | 1,000 requests; a fare with a link uses 2 |

One generation for one departure city uses at least 4 Gemini requests, about 5 Tavily credits and 6 Ignav requests. Results are cached for 24 hours in `backend/.local/`.

## Known limitations

- **Essential requirements rely on Gemini's own report.** Preferences are free text, so code checks the report, not the truth.
- **Hotel prices are estimates.** A quote may describe a different hotel, room or date. Availability on the trip dates is not checked.
- **`Sourced` means a source said it,** not that the fact was independently confirmed.
- **Booking links.** Ignav links are rejected when their own parameters contradict their direction or dates, which can only be checked when the link includes them. A flight from the web search has no links and is reported as `round_trip`.
- **Ignav fares can change.** Ignav says a search price is not a reserved fare or a guarantee of one combined ticket. The round-trip cost may need separate bookings.
- **Multi-city trips** price a round trip to the first city only, which may not match the actual route home.
- **Airports.** Departure cities use a fixed Saudi table; an unlisted city falls back to web search. Arrival airports come from Gemini.
- **The budget check is incomplete** when a price is `Not available`, and excludes food and activities.
- **Currency rates are fixed and approximate.** `$` is assumed to be US dollars.
- **The destination conflict check compares words.** Essential `Istanbul` and `Turkey` count as a conflict, even though one is inside the other.
- **Reused proposals keep their old fares.** Unchanged inputs return saved proposals however long ago they were generated.
- **Quota.** At 20 Gemini requests a day, only a few generations fit, and regeneration uses more.
- **Free-plan privacy.** Check Google's current Gemini API terms before sending real members' preferences on the free plan.

## Proposal JSON changes for Developers 2 and 3

Source of truth: `backend/app/schemas/proposals.py`, mirrored in `frontend/src/types/proposal.ts`, with fictional samples in `docs/examples/proposals.mock.json`.

- `flights` is a list with one entry per departure city, and `origin` is required. A member's response holds only their own city.
- Status `Confirmed` is now `Sourced`.
- `SarPrice.status` can be `Sourced`, but only for flights. Hotel and transfer prices reject it.
- `Unconfirmed` values and prices may have an empty `evidence` list. `Sourced` and `Estimated` must have evidence, so check for an empty list before showing quotes.
- New `budget_status`: `within_group_budget`, `includes_unconfirmed` or `over_group_budget`. It never reveals the budget.
- `sources` holds only sources that are cited.
- New `flights[].trip_type`: `round_trip` (one booking), `split` (two bookings, total is `Estimated`) or `one_way` (return not counted, so `budget_status` is `includes_unconfirmed`).
- New `flights[].legs`, one or two entries with `direction` (`outbound` or `return`), `date`, `airline`, `duration`, `price` and `booking_url`. On a `round_trip`, both legs share one link and leg prices are `Not available`, so use `price_per_person`.
- New `cities[].booking_url`: a Booking.com search built from the hotel, city, country, dates and group size. It uses the city alone when the hotel is unknown. It does not confirm availability or price.
- Every `booking_url` is an `https` link or `null`. Links are separate fields; do not read them from `sources`.
