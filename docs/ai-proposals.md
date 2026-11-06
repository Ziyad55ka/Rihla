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

## Fare-first generation (3 November 2026)

Used whenever `IGNAV_API_KEY` is set. Without it, the web-search flow above is unchanged.

Problems it fixes: generation took 3-5 minutes, some runs ended with no result, and
some flights showed a web number with no booking link or a Google Flights search.

1. Gemini suggests `PLANNER_OPTION_COUNT` (5) trips in one request.
2. Code checks dates, requirements and privacy with no outside request.
3. Ignav checks each trip from every departure airport at the same time, with everyone
   from that airport in one search. A day with no fares moves by `FLIGHT_DATE_SHIFTS`
   (+1, -1, +2, -2), only inside the shared dates and never sooner than
   `MIN_DEPARTURE_LEAD_DAYS` (3) from today.
4. The first 3 trips with fares are researched at the same time (Tavily searches,
   departure cities and hotels also run together). Research is told a departure city
   with an airport must have a live fare, so a price is never shown without a link.
5. Fewer than 3: Gemini is asked once more, told those routes had no flights.
   None: `409` with `code`, `places` and `suggestions` (change dates, open preferences,
   try again). Messages name places only, never members, budgets or cities.

`GET /api/trips/{id}/proposals/progress` (members only) returns the current step and
each destination's status, moved dates and hotel price per night. It holds no private
data and lives in memory, so it needs a single backend process.

Hotel prices: with `SERPAPI_API_KEY`, Google Hotels (SerpApi) gives a 3-4 star hotel
rated 4.0+ for each city's own nights, priced per night in SAR. One more request opens
the hotel's page to prefer Booking.com's own price and link. Prices stay Estimated
because they change by the hour. About 2 requests per city per proposal: the free
plan (250 a month) covers roughly 30-40 generations.

Rihla does not scrape booking sites. Their terms forbid automated access, and avoiding
blocks would mean hiding that a bot is asking. Licensed APIs (Ignav, SerpApi) are used
instead.

## Privacy decisions

- Budgets and preferences stay in the backend. They never appear in a proposal.
- The planner receives no member labels or departure cities. It does receive the lowest budget and the preference text.
- Departure cities are sent to Ignav or Tavily, and to Gemini during extraction, without member identity.
- Titles and explanations are rejected if they contain a member's budget figure or departure city. Explanations also reject any digit.
- A stored proposal holds flights from every departure city. `rihla_get_proposals` returns only the caller's city and the sources still cited, inside the database. See [the flight visibility decision](#decisions).
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
- **Fares and seats are live and not guaranteed.** Ignav returns no seat count, and its documentation says a link does not confirm price or availability.
- **Seller pages can expire, or may not open the exact flight.** A link is checked against its own parameters and an airline's own site, which cannot catch every wrong page. An outside agent's link cannot be checked for its airline.
- **Limits lead to Google Flights.** Above a limit, or when a flight is gone, people get a search instead of a checked link. Google may ignore the passenger count.
- **The city hint.** "Available for all travellers from your city" can suggest that someone else departs from the same city.
- **Rooms for the group cannot be fully confirmed.** A search link asks for the group's size and one room for each person. Availability is checked only on the booking site.
- **Limits are counted on one server,** in a local file. Several servers would each count alone.
- **Older proposals** have no flight numbers, so the same flight is matched by airline name alone. Airline names follow Ignav's SA market and can stay in Arabic on the English page. City names outside a fixed table stay as written, until a new generation stores Arabic names.
- **A flight from the web search** has no links and is reported as `round_trip`. Its Book button needs airports, so it goes to Google Flights.
- **Ignav fares can change.** Ignav says a search price is not a reserved fare or a guarantee of one combined ticket. The round-trip cost may need separate bookings.
- **Multi-city trips** price a round trip to the first city only, which may not match the actual route home.
- **Airports.** Departure cities use a fixed Saudi table; an unlisted city falls back to web search. Arrival airports come from Gemini.
- **The budget check is incomplete** when a price is `Not available`, and excludes food and activities.
- **Currency rates are fixed and approximate.** `$` is assumed to be US dollars.
- **Conflicts Gemini finds are not shown early.** A doubtful destination conflict passes stage 1, so the trip page shows no conflict until someone generates.
- **Departure cities can be learned by experiment.** A member who changes their city to another member's city receives that city's flights, which shows someone departs from there, but not who. The team accepted this.
- **Quota.** At 20 Gemini requests a day, few generations fit. `MAX_GEMINI_CALLS_PER_GENERATION` (default 7) limits the requests a generation starts; one provider retry can pass it by one.
- **Older proposals have no change signal.** Proposals saved before fingerprints existed keep only the departure city check until the next generation.
- **Older proposals have one title.** Without `title_ar` and `title_en`, the page shows `title` in either language. Other generated text, such as hotel names and adjustment explanations, stays as Gemini wrote it.
- **Evidence reaches the browser.** The page no longer shows `evidence`, but it stays in the API response, so it can be read in the browser's network tools. Removing it from the response is planned if time allows after the trial.
- **The final price is only confirmed at checkout.** Every price is the last one a source reported.
- **Sources reuse results.** Ignav may return a fare fetched up to 30 minutes earlier, with no documented way to force a new one. `priced_at` holds the time the source fetched it, so a price just refreshed can still say 25 minutes.
- **A search's price can belong to another seller.** On Gulf Air RUH to BAH the search showed 900, which was flynas's, on the same flights. Gulf Air's own price was 1,614, and that matched its site. Rihla shows the seller it links to, but only a person checking the site can confirm a price: see [the accuracy results](price-accuracy.md).
- **Airline sites show the outbound price first.** Ignav gave one total on every route measured, so the page explains this rather than inventing a split.
- **The cheapest fare may leave out bags.** In the trial Ignav returned no `bags` and no `fare_name`, so the page usually says the bag may not be included. A search with `checked_bags=1` returned the same price with baggage status `unknown`.
- **Not every airline has a direct link.** Gulf Air and flynas gave results pages, and Aegean gave a posted form that cannot open from a link. Lufthansa's link held the flight numbers. `exact` is worked out from those numbers when the source does not say.
- **Trip.com was evaluated and excluded.** Its routes return 404, and its terms forbid links to anything but its home page. It stays off, and its terms need review or an agreement before any commercial use.
- **The fare table is general.** `app/data/airline_fares.json` describes each airline's cheapest fare, not the ticket. Only Gulf Air (a manual check) and flydubai (its own site) have a bag value; the rest say to check the airline's site.
- **No hotel photos.** No photo is taken from any site without permission, so hotels link to Booking.com for photos. City photos are from Wikimedia, by exact page title, so an unclear name gives the designed panel instead.
- **No stations on transfers yet.** The route line shows cities until generation fills `from_station` and `to_station`.
- **Limits are local.** Requests are counted in a local file, so several backend servers would not share them. The 2 minute button wait is only in the browser.
- **Free-plan privacy.** Google may use data sent on Gemini's free plan, and the lowest budget, preference text and departure cities are sent to it without names. Production needs a paid account. Check Google's current terms.

## Booking and payment are out of scope

Rihla ends at the Final Plan, defined in Sprint 0 as: "The final version of the selected proposal saved by the administrator. Members can view it in Rihla, but it does not mean that flights or hotels have been booked or paid for." Rihla does not book or take payment. Flight and hotel links only send people to outside sites, in a new tab. Rihla saves nothing about a booking.

## Flights for the group

Each departure city is searched with `adults` set to everyone flying from it. Ignav has no seat count, so a flight returned by that search is treated as having room for all of them. If the search returns nothing, the page says one flight may not fit everyone, and `budget_status` cannot be `within_group_budget`. A member never sees a count, only "available for all travellers from your city".

A trip on one airline both ways is preferred. A different trip replaces it only when it saves at least `SPLIT_MIN_SAVING_PERCENT` (15) and takes no more than `SPLIT_MAX_EXTRA_DURATION_PERCENT` (30) longer. This can add one Ignav request for each departure city.

Flight sources are asked at the same time. See [Sources](#sources). Ignav's documentation does not say whether an amount covers one passenger or the whole party, so we tested it on 1 November 2026: RUH to BAH, 20 to 30 November, with `adults` 1 and 2. All 54 itineraries matched by flight number, and each cost about twice as much for 2 adults (900 and 1,800 SAR on Gulf Air). So an amount covers the whole party, and `IGNAV_PRICE_SCOPE` defaults to `total`, which divides by the party.

When more than one person flies from a city, the same flight is also searched with `adults=1`, which costs one more request, or none from the cache. If booking alone saves at least 1 SAR per person, `price_per_person` becomes that price, `fare_basis` is `solo`, booking checks that one-person fare, and the page warns that people may not share a flight. Otherwise `fare_basis` is `group`. The budget check always uses `price_per_person`.

`rihla_flight_group` is in the migration for Developer 3's group total, and no code in this branch calls it. It stays there so the file matches the applied database.

## Sources

| Source | Used for | Cost | State |
| --- | --- | --- | --- |
| Ignav | Flight search, seller links and seller prices | First 1,000 requests free once, then paid | On when `IGNAV_API_KEY` is set |
| Trip.com AI plugin | Evaluated and excluded | No key, no stated price | Off: `TRIPCOM_ENABLED=false` |
| Tavily and Gemini | Hotels from approved booking sites, ideas for an area | Free plans | On |
| Wikimedia | City and destination photos, with credit | Free, no key | On: `PLACE_IMAGES_ENABLED=true` |

`FLIGHT_PROVIDERS` and `HOTEL_PROVIDERS` set the order, and `app/services/travel_providers.py` holds the shared shape and how to add a source.

**How the best price is chosen.** All sources are asked at once for the same route, dates and party. If the same flight is in more than one, the winner is the airline's own price, then a link to the flight itself, then the newest. Above `PRICE_CONFLICT_PERCENT` (10) between sources, the price closest to the airline's wins and the gap is logged. A source that fails or reaches its limit is skipped, and when none is left the person gets a search link.

**The seller's price comes first.** A search shows one price, but each seller on the booking link has its own. Rihla shows the price of the seller it links to, with `price_source` set to `seller`, preferring the airline itself. If that is above the search's by more than `PRICE_CONFLICT_PERCENT`, generation tries another airline, and a check suggests one. An agent cheaper than the airline by `AGENT_CHEAPER_PERCENT` (5) is offered as an option and marked as an agent. Every comparison is recorded: see [the accuracy results](price-accuracy.md).

**Each direction's price.** Ignav's booking links gave one total for the trip on all 8 flights measured, so the page shows the total and says the airline's site may show the outbound price first. If a seller ever states both directions and they add up, the page shows "outbound + return = total". A total is never divided.

### Trip.com: evaluated and excluded

Excluded because its routes return 404 and its terms forbid links to anything but its home page. It stays off, and its adapter remains in case that changes.

Trip.com is used for an academic, non-commercial purpose according to its terms. Its terms must be reviewed, or an agreement reached with Trip.com, before any commercial use.

> Trip.com مستخدم لغرض أكاديمي غير تجاري حسب شروطه، ويجب مراجعة الشروط أو الاتفاق مع Trip.com قبل أي استخدام تجاري.

Checked on 1 November 2026, against [the terms](https://www.trip.com/contents/service-guideline/terms.html?locale=en-XX) updated on 25 August 2026:

| Rule in the terms | What Rihla does |
| --- | --- |
| No commercial use of content without a licence, and the site is for "domestic and private use" | Off by default, academic use only |
| "You must not ... create a link to any part of our Website other than the home page" | Only links the API itself returns, unchanged. **This wording may not allow them, since the terms do not mention the API. Decide before relying on it.** |
| Trip.com must be acknowledged as the author | "Trip.com" is shown beside each price and link from it |
| No photos separately from their text | Hotel photos are not used. The API file has no image field anyway |
| No framing | Links open in a new tab |

The terms do not limit it to AI assistants, ban storage or set a rate limit, but the plugin file does describe itself as a "travel assistant" and asks for the user's original words. Rihla sends a plain description of the search with no private data.

**It does not work today.** The published file, `https://www.trip.com/ai-resource/trip/openapi.yaml`, and the routes `/searchFlightTicket` and `/searchHotel` on `www.trip.com` and `us.trip.com` all returned HTTP 404 on 1 November 2026. The code follows the copy archived on 1 May 2026. Switched on, it fails quietly and the next source answers. It has no passenger count, so a ticket's price is multiplied by the party, and seats for a group are not checked.

## The light flight update

Both actions check one trip with every source switched on, always asking directly with no local cache. They never use Gemini or Tavily, and never change the destination, cities or hotels.

- **Book:** `POST /api/trips/{trip_id}/proposals/{proposal_id}/book-flight?leg=outbound|inbound|round_trip`. A saved link is never used. It finds the same flight again, saves the new price, and returns a new link, checked against the airline, route and dates. It is now a POST, because it saves.
- **Refresh:** `POST /api/trips/{trip_id}/proposals/{proposal_id}/refresh-flights`. Updates the caller's city's flights, `priced_at`, availability and `budget_status`. The page then reloads and shows the new price with the difference.

Each works only on the caller's own departure city. Both read and save through the secret key, because the backend needs a traveller count and the lowest budget that no browser may see.

| What it finds | What happens |
| --- | --- |
| The same flight, with a link | New price and link. A `link_valid_minutes` timer starts, and when it ends the page asks for a new check |
| The same flight, with a results page | The page says which flight number and time to choose |
| The same flight, with no link that opens | `no_link`: price updated, Google search, and another flight offered with a link |
| The seller far above the search | The seller's price is saved, and a cheaper airline is offered as a suggestion |
| The flight is gone | The best replacement is saved in its place, with a card comparing it. Over budget is stated |
| No replacement anywhere | `not_available`: Google Flights search, filtered by airline, date and party where possible |
| No source answered | `check_failed`: says nothing was checked, and never that the flight is gone |

| Setting | Default | Meaning |
| --- | --- | --- |
| `FLIGHT_CACHE_MINUTES` | 15 | How long generation may reuse a fare. Refresh and book never do |
| `MEMBER_FLIGHT_ACTIONS_PER_HOUR` | 5 | Book or refresh presses per member |
| `TRIP_REQUESTS_PER_DAY` | 30 | New requests per trip, for each source |
| `DAILY_REQUESTS_PER_SOURCE` | 200 | New requests for the project, for each source |
| `REFRESH_COOLDOWN_MINUTES` | 2 | How long a button stays off after a press |
| `LINK_VALID_MINUTES` | 15 | The timer. Ignav's docs give no lifetime, so this is an assumption |
| `PRICE_CONFLICT_PERCENT` | 10 | The gap that counts as prices disagreeing |

A book or a refresh costs 2 requests with Ignav. Add 1 when refreshing for more than one person from a city, and up to 2 when another flight has to be found.

Usage is logged in `backend/.local/flight-usage.sqlite3`, with no private data: members appear only as a hash. See it with `uv run python -m app.services.flight_usage`.

## The real measurement

On 1 November 2026, a person compared Gulf Air's site with Rihla, RUH to BAH, 20 to 30 November, Economy Light: outbound GF 162 at 06:50 was 999.00, and the return at 01:25 was 615.00. **The total was 1,614.00, exactly Rihla's price, a 0% gap.** The 998.50 seen before was only the outbound price, because the site shows that first and adds the return afterwards. The fare included a 25 kg bag.

Other airlines are in [the accuracy results](price-accuracy.md), waiting for the same check.

## Why a refresh once showed no change

Diagnosed with real requests on 1 November 2026, RUH to BAH, 20 to 30 November, one adult.

| Check | Result |
| --- | --- |
| Our 15 minute cache | The trial's refresh was served from it: logged as `cached=1`, 63 seconds after the search |
| Ignav's own reuse | Up to 30 minutes, with `observed_at` keeping the first time. Seen on the CDG search, 20 minutes old. No documented way to force a new one |
| Which price was read | The search's 900, which was another seller's. The link it opened was Gulf Air's at 1,614, so the page and the link disagreed. This was the main fault, and also why booking showed 900 |
| Saving | The secret key cannot read `proposals` directly, by design, so the saved row was not inspected |
| France's "no longer available" | Wrong message. The flight existed, but Aegean's only link was a posted form that Rihla rejects, and that was reported as gone |

| RUH to BAH | Search | Seller | Link |
| --- | --- | --- | --- |
| Gulf Air GF 162, GF 163 | 900 | flynas 900, a mismatch, rejected. Gulf Air 1,614 | Results page |
| Gulf Air GF 170, GF 189 | 900 | Same as above | Results page |
| flynas XY 233, XY 234 | 1,000 | flynas 1,000 | Results page |

## Price age

`priced_at` is saved for every flight and hotel price. Older proposals use the generation time.

| Age | Label |
| --- | --- |
| Under `PRICE_FRESH_HOURS` (3) | Updated X minutes ago |
| Up to `PRICE_STALE_HOURS` (24) | X hours ago, may have changed |
| Older | Old price, refresh before booking |

## Stay sources

Sources are classified by domain with `BOOKING_DOMAINS`.

- **Booking and price sources:** Booking.com, Agoda, Expedia, Hotels.com, Airbnb, Marriott, Hilton, IHG, Accor, Hyatt, KAYAK, momondo, trivago, Trip.com and Google Hotels (`google.com/travel` only). Only these can name or price a hotel. Whichever one supplied the price, the button is a Booking.com search with hotel, city, country, dates, `group_adults` and `no_rooms`, assuming two people per room.
- **Sources for ideas:** everything else, including blogs and guides. They can suggest an area, but never a hotel name, a price or a button.

When a hotel source is switched on, its hotel replaces the web search's, with `hotel_url` for its own page and `hotel_source` for its name. Booking.com stays as the comparison. Gemini never chooses a hotel or a price.

The rule also runs when reading, so older proposals follow it: a hotel from any other site is hidden and replaced by a search of its city. Generation runs one ideas search per proposal and one search limited to booking sites per city, which adds one Tavily search per proposal. Preferences are not put in these searches, because queries leave the system.

## Stations on transfers

Transfers have `from_station` and `to_station`, which the page shows when present. **Nothing fills them yet.** To fill them, generation needs one more field per transfer in `build_search_plan` for each station, with `verify_field` requiring the name in the source's own words, then these fields set in `build_proposal`.

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

`rihla_trip_generation_inputs(trip_id, admin_id)` returns members' private inputs under anonymous labels. It and `rihla_save_proposals` are granted only to `service_role`, and `authenticated` cannot call them. Only `backend/app/services/generation_inputs.py` uses `SUPABASE_SECRET_KEY`. Because the key has no signed-in user, the backend must verify the account first and pass its id. See [the decision](#decisions).

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

With `PROPOSALS_DEMO_MODE=true`, generation serves `app/data/demo_proposals.json` with no Gemini, Tavily or Ignav requests, and booking gives a search link. It still needs Supabase.

```powershell
# Backend tests, including tests/proposals
cd backend; uv run pytest
# Database tests: Sprint 1, then proposals
cd supabase; npm test; node --test tests/proposals.test.mjs
# Frontend
cd frontend; npm test; npm run lint
```

## Decisions

### Flight visibility (31 October 2026)

- Sprint 2 searches flights from every departure city in the group. Those cities are sent to the search provider without member names.
- The stored proposal holds flights for all cities. `rihla_get_proposals` filters inside the database, so a member receives only flights from their own departure city, and no sources cited only by other cities' flights.
- Browser roles have no direct access to the proposal tables. The filter is in SQL because a function granted to `authenticated` can be called directly, bypassing the backend.
- If a member's departure city changes after generation, the page asks the administrator to generate again. Until then, changing to another member's city shows that city's flights, which reveals that someone departs from there but not who. The team accepted this as a known limitation on 2 November, because trips are among friends.
- Reviewable: the team may later show every city's flights to everyone without names, as was done for dates on 21 October. That change needs a migration to `rihla_private.proposal_for_member`, plus updating this rule.

### Sprint 2 update: reading private inputs for generation (2 November 2026)

- **Decision:** Group conflicts are calculated inside SQL and return categories only. Generation inputs are read with a Supabase secret key kept in `backend/.env`. The key is used in one module, `generation_inputs.py`, for two calls: reading generation inputs and saving generated proposals. `rihla_trip_generation_inputs` and `rihla_save_proposals` are never granted to `authenticated`.
- **Why:** This narrows the earlier decision against using `service_role`. A function granted to `authenticated` can be called directly from a browser with a member's token, bypassing FastAPI. A generation function open to that role would let a trip administrator read every member's budget and preferences, which breaks the privacy rules above. Saving was added on 2 November because an administrator with a save function could otherwise store invented proposals or booking links for their group.
- **What stays the same:** All other requests keep the publishable key plus the user's token, under Row Level Security.
- **Risk accepted:** The secret key bypasses Row Level Security, so it must never reach a browser, a log or Git. Automated tests check that only one module uses it and that the browser role cannot call the function.
- This update authorizes no remote migration, deployment or push.
- **Condition for the upcoming endpoint:** Before generating or regenerating, it must verify the signed-in account through Supabase Auth and confirm that account is the trip administrator. It must pass only that verified id to the functions in `generation_inputs.py`, never an id from the request.

### Fit score and multi-city flights (5 November 2026)

- **Fit score (US-15-AC03).** Each proposal now has `fit`: the group average and
  the percent for the least-satisfied member, with no names. Dates and budget count
  3 for every member; each member's own preferences count 3 when Essential and 1
  when Flexible. Met counts fully, unverified counts half, unmet counts zero.
  Proposals are ordered by the least-satisfied member first, then by the average.
- **Combining preferences.** The planner is told to combine two wishes in one trip
  when they fit (two cities next to each other), to find one place that bridges
  them, or to pick one and say who gives way.
- **Flights home from the last city.** A trip such as Paris then Barcelona flies
  out to `CDG` and back from `BCN`. The planner gives `return_airport`; Ignav is
  asked with its two-leg search, and `Flights.return_airport` stores it so a price
  refresh asks for the same flights. Trip.com is skipped for these trips because it
  only books round trips. One-city trips are unchanged.

### Live test feedback (5 November 2026)

Changes after the first live test, each tied to a Nielsen heuristic or a user story:

- **Sign-in errors (Nielsen 9).** Supabase now reports the reason in `error_code`
  (with the HTTP status in `code`), so a wrong password was shown as "check the
  backend". `auth_error_code` reads both shapes. The page now tells apart a wrong
  password (with "New to Rihla? Choose Sign up"), an unreachable server, a failing
  sign-in service and an incomplete email.
- **Invitation code (Nielsen 4 and 7).** Six digit boxes with `one-time-code`,
  paste fills every box, and pasting a link switches to the link field.
- **Places are wishes.** Destinations and flight preferences have no Essential or
  Flexible choice and are always saved as Flexible, because the planner combines
  everyone's places. Older Essential places no longer block generation
  (`GroupConflicts` drops the `destinations` category) and different countries are
  never a stage-one conflict.
- **Progress list.** A place with no bookable flights shows for 2.5 seconds, then
  leaves the list; a line counts the places skipped. One or two proposals are still
  returned when fewer than three have flights.
- **Retry advice.** "Try again in about 2 hours" (`RETRY_AFTER_HOURS`), since fares are
  cached for minutes only.
- **One cost rule (US-13, US-15).** The budget check now adds the same parts as the
  cost page, meals allowance included, so a proposal accepted at generation cannot
  show a higher total on its page. A hotel night or transfer with no live or web price
  takes the planner's typical price, shown as "Rough estimate · Check before booking"
  (`Unconfirmed`), so no cost is left out of the total.
- **Flight not offered by the seller.** Search data can lag behind the airline (Riyadh
  Air showed no RX 531 on 8 November while the search still listed it). Under the
  booking button, "Find another flight" calls `POST .../flight-not-offered`, which
  looks for another airline first, then any other flight.
- **How it matches the group.** The fit score, trade-offs and "AI can make mistakes"
  lead. The per-topic checks (US-15-AC01/AC02) stay one click away under "See each
  check".
- **Every flight checked on a second source.** Ignav's data can lag behind the
  airline, so a kept flight must also be sold on Google Flights (through the SerpApi
  key) with the same flight numbers, both ways, on the same dates
  (`google_flights_check.py`, `verify_flights_on_google`). At generation, cheaper
  itineraries Google does not list are skipped for one it does; with none, the
  option has no flights and the next place is tried. Book checks again before it
  opens a link, and replaces a flight Google no longer lists. A check that fails
  (no key, outage) never removes a flight, but the page then makes no claim: the
  "Also on sale on Google Flights" chip shows only when both sources agree. Cost:
  about two SerpApi requests per departure city and proposal.
- **Sources folded.** The sources list moves to a folded "Where this information
  comes from" line at the end of the page. US-14-AC01 still needs it reachable.
- "AI can make mistakes" also shows under the proposal list.
