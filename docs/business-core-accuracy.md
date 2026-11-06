# Business core accuracy — local implementation

The language model proposes routes and reads guide sources. It is not the authority
for ticket inventory, a guaranteed fare, hotel availability or event dates.

## Flights

- Live generation and refresh accept outbound and return only when the supplier
  sells both in one booking option with one matching HTTPS booking URL. Separate
  one-way links remain classified as split, even if cheaper, and are rejected.
  The public booking endpoint accepts only `leg=round_trip`. The two-step split
  booking interface is removed; legacy split/incomplete offers need regeneration.
- When the cheapest itinerary only offers separate tickets, generation tries up
  to three distinct candidates, including a dearer joint ticket on the same
  airline. Fare and generation caches are versioned for the policy; a cached
  separate fare is revalidated rather than reused. Explicit airline deep-link
  dates, airports and passenger counts cannot contradict the request.
- A multi-city trip returning from its arrival airport must end with an explicit
  stay in the arrival city, including a final night and the ground transfer in
  the normal city sequence. This prevents silently omitting Bursa–Istanbul or
  Alexandria–Cairo. A real single-booking open-jaw ticket is still supported.
  Existing incomplete ground routes are marked for regeneration on API reads.
- Generation retains Ignav with the existing SerpApi / Google Flights second check.
  Contradictory supplied airport/date facts, airport changes within a connection,
  invalid prices and a return arriving after the allowed final day are rejected.
  An invalid cheap itinerary no longer hides the next valid alternative.
- Party fares are divided by that route's traveller count. A cheaper one-person
  search is informational and never reduces the fare quoted for the group.
- A search price is estimated. A seller quote and a search listing remain distinct;
  neither reserves seats. Refresh / Book still recheck through the existing flow.
- A second-source outage leaves `schedule_confirmed=false`, with a visible warning.
  This is a degraded result, not confirmed availability. Booking links can open a
  search rather than a pinned flight; their existing specificity flag is preserved.
- Empty valid responses mean no flights; malformed responses, authentication and
  provider failures mean source unavailable. A rejected credential/quota stops
  additional requests to that source during that generation instance.

## Cost and hotels

Generation compares the conservative unshared-room baseline against the minimum
member budget. Flight-only failures can stop before hotel/model research. Nearby
date alternatives remain inside the shared dates. Selected activities are added
afterwards and can change the budget outcome; unknown prices are never free.
New generations reserve SAR 75 per person per day for activities, in addition to
the configured meals allowance. Cost totals retain that reserve when saved choices
are cheaper and use the selected cost when higher. The reserve is unconfirmed,
not a promise that every activity can be purchased for that amount. Saving activity
choices checks the private minimum budget and all departure routes before writing;
a failed budget lookup prevents the write without exposing anyone else's budget.
The local `20261106000100_activity_budget_guard.sql` migration adds a database
trigger so calling the authenticated activity RPC directly cannot bypass known
cost/minimum-budget checks. It rejects missing member budgets and changed input
fingerprints too. The database floor is SAR 150/day for meals plus the activity
reserve; a larger backend meal setting is additionally checked by the API. Changing
that floor requires reviewing the migration alongside configuration. It has been
tested only in the isolated database and is **not applied to hosted Supabase**.
Until applied, the local API has the extra checks but the hosted RPC retains its
previous rules. No production database changes were made.

Hotel stars are encoded in the existing private accommodation preference, with
explicit consent to each lower class. Legacy notes remain editable. The shared
hotel search uses the intersection of accepted classes; empty intersections block
generation. SerpApi's fallback retains the class filter and checks the actual
hotel class rather than its review score. Essential classes require a verified
matching hotel class. When no search, average or planner price exists, the
stay uses `HOTEL_FALLBACK_NIGHT_SAR` (400 by default), marked Unconfirmed, so a
hotel is never counted as free against the minimum budget. If a specific quote is missing but at least two eligible
dated comparables have prices, their arithmetic average is labelled as a market
allowance, with no named hotel. No samples means no fabricated average. Nightly
prices prefer the returned tax-inclusive value when available.

Display and cost calculation apply the same source policy. SerpApi hotel offers
keep their observed Google Hotels price URL separately from the hotel's navigation
URL. An unapproved hotel website is not promoted to an approved price source.
Both main costs and activity estimates include the configured daily allowance for
meals and small expenses. This allowance is explicitly unconfirmed. Selected
restaurants are additional costs; the allowance is not reduced automatically.

## Landmark content and photographs

Activity extraction requests Arabic and English names and descriptions in the
existing model call, translating only cited facts. Page reads do not invoke a
model. Public enrichment resolves canonical names without parenthetical aliases,
checks name and city identity, rejects disambiguation pages, and uses linked
Arabic articles where available. Photos retain creator, licence and a credit link.
Missing city photos no longer stop activity enrichment.

When the Wikimedia API is unavailable, public article introductions and Openverse
provide independent fallbacks. Openverse photos require a matching name and city,
an accepted reusable licence, HTTPS and a non-mature listing. Requests are bounded
and rate limited; quota failures pause that source. A matching title is a useful
identity check, not a visual guarantee. A failed photo or translation does not
discard the other content. Cache misses and incomplete content expire in five
minutes; complete bilingual/photo content lasts 30 days. Cold reads are bounded
and may still show placeholders when a source is slow.

A small reviewed bilingual catalogue covers twelve popular landmarks in Madrid,
Córdoba, Paris and Istanbul. It is a fallback, not global city coverage. Four adult admission
references have conservative SAR planning allowances, explicit original EUR/TRY
tariffs, official references and a 6 December 2026 expiry. They never overwrite an
existing numeric provider price backed by evidence. Unsupported model estimates
can be replaced by the reviewed tariff allowance. Source policy applies these guides consistently
to display, activity estimates and the private budget guard. Missing prices can
remain unavailable; model-only activity allowances are marked Unconfirmed rather
than provider quotes. No unknown price becomes free. Four exterior photographs of
Madrid landmarks were visually reviewed, with their Openverse/Flickr licence and
credit metadata retained. Metadata alone was insufficient: some search results
named the Royal Palace but actually showed the neighbouring cathedral. Reviewed
photos take priority for those specific landmarks. Other images still rely on
source identity checks and can remain unavailable. The frontend attempts a source
thumbnail if the original photo fails, and reveals credit links through the info
control. A low intersection threshold prevents very long mobile activity lists
from remaining hidden by the scroll animation.

## Dated events

`TICKETMASTER_API_KEY` is optional, backend-only and empty by default. No account,
key or billing plan is created automatically. Existing guide research stays active.

The optional Discovery adapter makes one bounded request per city. It requires a
matching city/country, a precise date within that city's stay, a trusted purchase
domain and an on-sale listing. Cancelled/postponed/rescheduled/offsale, TBA/TBD,
closed/future public sales, invalid prices and duplicate ids are filtered. The
upper advertised range is estimated in SAR; unknown admission remains unavailable.
Fees, seats and checkout are not confirmed by Discovery. Location aliases and
market coverage are deliberately limited; an empty result is not proof no local
event exists. No claim that API ranking measures trending popularity is made.

Structured events bypass Gemini extraction and can survive a model failure.
Partial-source notices are stored inside activities, which the existing Supabase
research RPC preserves. No migration is needed. Existing ready research is cached;
partial results currently retain that same cache lifecycle.

## Models and retry

`GEMINI_EXTRACTOR_MODEL` optionally separates extraction from planning; blank keeps
the planner model. Evaluate available Gemini 3.x models with the project's schema
and evidence checks before changing the setting. There is no silent model switch.
Quota hints use sanitized quota identifiers and retry durations, not raw provider
messages. A daily reset is a retry opportunity, not a promise the request will pass.

## Local validation

Hotel ad redirects are not offered as hotel pages. A dated comparison or the
named hotel's Booking search remains available when a direct page is missing.
Flight and hotel amounts render immediately instead of animating from zero.
Changed group inputs invalidate budget and compatibility claims in both cards
and details until regeneration; the previous estimates remain readable.

Proposal cards and details show an advisory flight-price review reminder. The
backend sets `PRICE_REVIEW_MINUTES` (15 by default). It starts at the oldest actual
`priced_at` across the visible round-trip routes, never at page load or generation
time. Missing timestamps, incomplete round trips, unconfirmed schedules or group
availability require another check. Expiry neither ends the trip nor holds a fare;
the existing booking action still requests a fresh supplier check. The bottom
source appendix is removed from the page, while validation evidence and photo
license credits remain available internally and beside each photo respectively.

Backend: `.venv/bin/pytest -q`, `.venv/bin/ruff check app tests` and formatting check.
Frontend: `npm run lint`, `npm test`, `npm run build`.
Supabase: `npm test` uses disposable in-memory PostgreSQL with real migrations and
simulated Auth roles, not the hosted database. Live supplier checks must use
synthetic travel queries, with no booking, payment or trip writes.
