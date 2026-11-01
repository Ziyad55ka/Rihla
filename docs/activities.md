# US-11 and US-12 — Ziyad

## Local demo

From `frontend`, run `npm ci`, then `npm run dev`. Open
`http://localhost:5173/demo/activities`.

This development-only page needs no login, Supabase credentials, AI key, or backend.
It uses synthetic proposals from `src/data/activities.mock.json`. Select activities,
save, refresh, switch proposals, and remove selections. Demo selections live only
in this browser and are isolated by trip, proposal and generation version.
An unavailable price remains unknown rather than becoming zero; a free activity
has an explicit zero price. The displayed activity subtotal is per person and
separate from the proposal's existing budget status.

## Shared schema additions

`CityStay.activities` defaults to an empty list, preserving saved proposals without
activities. Each activity has a UUID, name, description, location, duration,
scheduled date, price per person, optional HTTPS booking link, and optional HTTPS
image URL. Text and date fields use `InfoField`; the price retains `SarPrice`'s
status and evidence contract, with zero permitted only by `ActivityPrice`.
Activity prices cannot be `Sourced`, preserving the team's live-flight-only rule.

Dates use ISO calendar dates and must fit the activity's city stay. Activity UUIDs
must be unique within the proposal. `evidence_fields()` includes every activity
field so source validation and source pruning continue to work.
The Python and TypeScript definitions, shared mock, and frontend mock are updated.
The AI generation pipeline is unchanged: Developer 1 must supply the activities
according to this schema when enabling real activity generation.

## Main design reference

The supplied main archive's `styles.css`, `workspace.css`, `navbar.css` and
`planning.css` were compared byte-for-byte with the Sprint 2 base: they match.
Those CSS files and the original LandingPage are unchanged. The demo reuses `Brand`, `LanguageSwitcher`, the original landing shell, `rihla-navbar`, `ProposalsView`, `trip-primary`,
`trip-secondary`, and `planning-member-card` from that design. Added activity CSS
uses the existing `--rihla-*` variables, card borders, spacing and type treatment.
The activities appear below the selected proposal, rather than squeezing three
activity panels inside the three proposal summary cards. Arabic and English are
supported; generated/mock content remains in its supplied language.

## Real persistence (prepared, not applied to a cloud database)

New migration: `20261103000100_activity_selections.sql`, after the existing proposal
migrations. It creates private per-member selections with RLS and no direct browser
table access. The authenticated RPCs infer the user from the session, check current
trip membership, verify proposal/version/activity IDs, and reject old proposals.
Regeneration deletes the old proposal rows and cascades their selections.
The public proposal ID is inside its JSON; the table row has a different internal
ID. The RPCs resolve the public ID and use the internal ID for the foreign key.

Backend endpoints:

- `GET /api/trips/{trip_id}/proposals/{proposal_id}/activities/selection`
- `PUT /api/trips/{trip_id}/proposals/{proposal_id}/activities/selection`

PUT body: `{ "version": 1, "activity_ids": ["uuid"] }`. Send an empty list to
remove all selections. It replaces only the caller's choices for that proposal.
The normal proposals UI uses these authenticated endpoints. No cloud migration has been applied. This work is intended for the Ziyad development branch only; main and the teammate branch are unchanged.

## Validation

- Frontend: lint, translation coverage, TypeScript, unit tests, production build.
- Backend: Ruff and pytest with fake external services.
- Database: migrations and access-control tests on local PGlite PostgreSQL.
- Browser: selecting, saving, refreshing, Arabic display and proposal switching.

## Development branch and integration

This implementation is based on the supplied sprint-2/ai-proposals archive,
matching commit 357ce2218af325df8d87bdaa5c3822bd9ccc20b0. It deliberately does not
incorporate subsequent teammate changes. Only Ziyad is the upload target.

The explicit Save activities button is retained by the user's preference.
This is a mock-backed development delivery, not a claim of full acceptance:
real activity generation and cloud persistence need integration testing, and
US-12-AC03 still needs integration of selected activity costs into the relevant
proposal estimate with the US-13 developer. A separate saved-activities page is
not required by US-12; access to the finalized plan is covered by US-24.
US-11-AC01 calls for activities, attractions and restaurants: the current generic
activity schema can carry them, but the demo currently has no restaurant fixture
or category filter. These should be checked during the acceptance review.

## Visual layout

The page opens with the existing navbar, a short heading, the three proposals,
and the selected proposal's activities. The large welcome hero and artwork are
not repeated inside this planning task. The original homepage is unchanged.
Synthetic example copy is localized without changing activity IDs or selection
keys. Cards include decorative line art when no photo is supplied. The missing
price status appears once per field. Lint, translations, TypeScript and the
production build pass after this layout change.
