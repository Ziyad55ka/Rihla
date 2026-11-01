# AI proposals (US-09)

How Rihla generates three trip proposals, and what the results can and cannot be trusted for. The routes and migrations are tested locally and have not been applied to the real Supabase project.

## Checks before generation

`generate_checked` in `backend/app/services/generation_precheck.py` is the entry point. It runs the cheapest checks first.

| Stage | Cost | Checks | On failure |
| --- | --- | --- | --- |
| 1 | No outside request | All members Ready, shared dates exist, no clear conflict between Essential destinations, lowest budget is at least `MIN_BUDGET_SAR_PER_DAY` per trip day (default 250), and whether saved proposals can be reused | Stops. Unchanged inputs return proposals saved within `SAVED_PROPOSALS_TTL_HOURS` (default 24) |
| 2 | No extra request: part of the first planning request | Whether Essential requirements, the lowest budget and the dates can fit together | Stops before any search. When unsure, Gemini is told to allow it |
| 3 | The rest of generation | See below | See below |

Stage 1 treats a destination conflict as clear only when every word in each Essential destination is a known country and they share none. Anything else, such as `Istanbul` and `Turkey`, goes to stage 2.

`generate_checked(regenerate=True)` skips saved proposals but still runs stage 1. The upcoming endpoint must allow it for the trip administrator only.

Failures raise `GenerationBlocked`, with messages by category only: `readiness`, `dates`, `destinations`, `flights`, `accommodation` or `budget`. They never name a member or a value, and Gemini's words are not shown. If every proposal fails on budget, the result is a `budget` message without the figure.

The inputs hash covers the trip, dates and every member's data, ignoring member order. It is keyed with `PROPOSALS_HASH_KEY` so budgets cannot be guessed from it, and no function returns it. The API stores results in the `proposals` tables; `backend/.local/generations.sqlite3` is used only when no store is passed, such as the spike. Only complete results are saved for reuse, and fares can change within the time limit.

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
- A stored proposal holds flights from every departure city. `rihla_get_proposals` returns only the caller's city and the sources still cited, inside the database. See [the flight visibility decision](sprint-1-decisions.md).
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

One generation for one departure city uses at least 4 Gemini requests including the feasibility answer, about 5 Tavily credits and 6 Ignav requests. Results are cached for 24 hours in `backend/.local/`.

## Known limitations

- **Essential requirements rely on Gemini's own report.** Preferences are free text, so code checks the report, not the truth.
- **Fewer than three proposals can appear.** Options that fail the checks or reach the request limit are left out, and the page says so.
- **Prices are estimates.** A hotel quote may describe a different hotel, room or date, and availability on the trip dates is not checked. A price with no source is Gemini's general estimate.
- **`Sourced` means a source said it,** not that the fact was independently confirmed.
- **Booking links.** Ignav links are rejected when their own parameters contradict their direction or dates, which can only be checked when the link includes them. A link can come from a different seller than the airline shown, and some may not open the exact flight. A flight from the web search has no links and is reported as `round_trip`.
- **Ignav fares can change.** Ignav says a search price is not a reserved fare or a guarantee of one combined ticket. The round-trip cost may need separate bookings.
- **Multi-city trips** price a round trip to the first city only, which may not match the actual route home.
- **Airports.** Departure cities use a fixed Saudi table; an unlisted city falls back to web search. Arrival airports come from Gemini.
- **The budget check is incomplete** when a price is `Not available`, and excludes food and activities.
- **Currency rates are fixed and approximate.** `$` is assumed to be US dollars.
- **Conflicts Gemini finds are not shown early.** A doubtful destination conflict passes stage 1, so the trip page shows no conflict until someone generates.
- **Departure cities can be learned by experiment.** A member who changes their city to another member's city receives that city's flights, which shows someone departs from there, but not who. The team accepted this.
- **Quota.** At 20 Gemini requests a day, few generations fit. `MAX_GEMINI_CALLS_PER_GENERATION` (default 7) limits the requests a generation starts; one provider retry can pass it by one.
- **Older proposals have no change signal.** Proposals saved before the `20261102000300` migration keep only the departure city check until the next generation.
- **Older proposals have one title.** Without `title_ar` and `title_en`, the page shows `title` in either language. Other generated text, such as hotel names and adjustment explanations, stays as Gemini wrote it.
- **Free-plan privacy.** Google may use data sent on Gemini's free plan, and the lowest budget, preference text and departure cities are sent to it without names. Production needs a paid account. Check Google's current terms.

## Booking and payment are out of scope

Rihla ends at the Final Plan defined in Sprint 0. It does not book or take payment. Flight and hotel links only redirect to outside sites, open in a new tab, and send nothing back; Rihla saves nothing about a booking.

## Regeneration signal

`needs_regeneration` is true when any member joins, leaves or changes generation inputs after generation, or when the caller's departure city has no flights. The database compares a fingerprint saved at generation with the current one. The fingerprint is never returned, and the page shows only a general message.

## Real trial, 2 November 2026

One real generation for a one-member trial trip on the real Supabase project, with destinations `France, Bahrain`:

| Result | Detail |
| --- | --- |
| Proposals | Two: Paris and Strasbourg (`includes_unconfirmed`), and Manama (`within_group_budget`) |
| Third proposal | Failed: `duplicate_route` and `over_group_budget` |
| Use | 11 Gemini requests, 102,179 tokens, 12 Tavily credits, 4 Ignav requests, 4 cached searches |

Changes made afterwards, not yet tried in a real generation:

- The planner is told to offer different cities in one country when few countries are allowed, or, for Flexible destinations, a nearby country with an explanation.
- A repeated route gets one explicit retry, then that option stops. The same cities under another name count as a repeat.
- A retry after `over_group_budget` asks for something cheaper, and the figure stays out of shown text.
- `MAX_GEMINI_CALLS_PER_GENERATION` stops a generation at its limit and returns what passed.

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

## Showing conflicts before generation

`rihla_get_group_conflicts(trip_id)` runs inside PostgreSQL, so no private data reaches the backend or the browser for this check. Any trip member can call it. It returns `conflicts` by category, `own_review` when the caller has an Essential destination in a conflict, and `can_generate`. It holds no member or value. A budget conflict gives no review notice, because that would tell a member their budget is the lowest. No route or page uses it yet.

The SQL repeats the stage 1 rules used by `generation_precheck.py`. A backend test keeps the country list and the default budget floor equal. The SQL floor is fixed at 250, so a changed `MIN_BUDGET_SAR_PER_DAY` also needs a migration.

A member can still learn something by experiment: changing their own Essential destination and watching whether the conflict clears shows whether another member's destination matches. Date conflicts have the same property.

## Private generation inputs

`rihla_trip_generation_inputs(trip_id, admin_id)` returns members' private inputs under anonymous labels. It and `rihla_save_proposals` are granted only to `service_role`, and `authenticated` cannot call them. Only `backend/app/services/generation_inputs.py` uses `SUPABASE_SECRET_KEY`. Because the key has no signed-in user, the backend must verify the account first and pass its id. See [the decision](sprint-1-decisions.md).

## API

| Route | Who | Does |
| --- | --- | --- |
| `GET /api/trips/{id}/conflicts` | Any member | Conflict categories, the member's review notice and `can_generate` |
| `GET /api/trips/{id}/proposals` | Any member | Latest proposals, with only the caller's flights |
| `POST /api/trips/{id}/proposals` | Administrator | Generates and saves. Body `{"regenerate": true}` skips saved proposals |

The POST route takes the database lock first, which also refuses anyone but the administrator before the secret key or any quota is used. A second request while one runs gets HTTP 409. A crashed run frees the lock after ten minutes. Conflicts return HTTP 409 with categories only.

Saving goes through the secret key, and `rihla_save_proposals` is closed to browser roles, so nobody can store invented proposals or booking links, including the administrator.

`rihla_get_proposals` also returns `needs_regeneration` when proposals exist but none has flights from the caller's departure city. The page then asks the administrator to generate again.

**Accepted limitation:** If a member changes their departure city to another member's city, they receive that city's flights until the next generation. This shows them that someone departs from there, though not who.

## Trying it locally

The preview server in `supabase/tests/` also covers these routes, with no outside services. Besides the steps in [the trip guide](trips-and-invitations.md), start the backend with `SUPABASE_SECRET_KEY=sb_secret_local_preview` and `PROPOSALS_DEMO_MODE=true`. The saved demo proposals depart from Riyadh, so a member from another city sees no flights.
